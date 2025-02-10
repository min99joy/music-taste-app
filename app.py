from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import logging
import requests
import re
import numpy as np
import json  # JSON 파일 처리를 위해 추가

# 가사 가져오기 및 감성 분석용 라이브러리 (TextBlob 대신 VADER 사용)
import nltk
nltk.download('vader_lexicon')
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import lyricsgenius

# .env 파일의 환경 변수 로드
load_dotenv()

app = Flask(__name__)

# 환경 변수에서 Spotify 클라이언트 ID, Secret, Genius 토큰 가져오기
client_id = os.getenv("SPOTIPY_CLIENT_ID")
client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
genius_token = os.getenv("GENIUS_ACCESS_TOKEN")

# Spotify Client Credentials Flow 설정
client_credentials_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

# Genius 객체 생성 (lyricsgenius 사용)
genius = lyricsgenius.Genius(genius_token, skip_non_songs=True, excluded_terms=["(Remix)", "(Live)"])

# 전역 VADER 감성 분석기 생성
sentiment_analyzer = SentimentIntensityAnalyzer()

# 디버그용: 액세스 토큰 출력
try:
    token_info = client_credentials_manager.get_access_token(as_dict=False)
    print("Access token:", token_info)
except Exception as e:
    print("Access token 발급 실패:", e)

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)

#############################################
# DECADE_GROUP_WEIGHTS: 발매 연도(데케이드)별 음악적 트렌드를 반영하는 가중치
#############################################
# 개선된 DECADE_GROUP_WEIGHTS 예시

DECADE_GROUP_WEIGHTS = {
    "1960s": {
        "칠 가이": 0.25,       # 차분하고 전통적인 느낌
        "미식가": 0.25,       # 섬세한 음악 감상
        "BGM 마스터": 0.15,   # 배경 음악으로 적합
        "클러버": 0.05,       # 클럽 분위기는 거의 없음
        "사운드 실험가": 0.05, # 실험적 요소는 미미함
        "클래식 수호자": 0.25  # 클래식과 전통적 가치 강조
    },
    "1970s": {
        "칠 가이": 0.20,
        "미식가": 0.20,
        "BGM 마스터": 0.15,
        "클러버": 0.20,       # 디스코와 펑크의 등장으로 댄스 분위기 상승
        "사운드 실험가": 0.10,
        "클래식 수호자": 0.15
    },
    "1980s": {
        "칠 가이": 0.20,
        "미식가": 0.20,
        "BGM 마스터": 0.15,
        "클러버": 0.25,       # 신스팝, 전자음악의 부상 → 댄스/클럽 분위기 강화
        "사운드 실험가": 0.10,
        "클래식 수호자": 0.10
    },
    "1990s": {
        "칠 가이": 0.25,
        "미식가": 0.15,
        "BGM 마스터": 0.15,
        "클러버": 0.25,       # 얼터너티브, 힙합 등으로 클럽 분위기와 에너지 상승
        "사운드 실험가": 0.10,
        "클래식 수호자": 0.10
    },
    "2000s": {
        "칠 가이": 0.30,
        "미식가": 0.20,
        "BGM 마스터": 0.10,
        "클러버": 0.20,
        "사운드 실험가": 0.10,
        "클래식 수호자": 0.10
    },
    "2010s": {
        "칠 가이": 0.25,
        "미식가": 0.20,
        "BGM 마스터": 0.10,
        "클러버": 0.30,       # EDM과 클럽 문화의 영향
        "사운드 실험가": 0.10,
        "클래식 수호자": 0.05
    },
    "2020s": {
        "칠 가이": 0.25,
        "미식가": 0.20,
        "BGM 마스터": 0.10,
        "클러버": 0.25,
        "사운드 실험가": 0.15,  # 다양한 실험적 음악의 부상
        "클래식 수호자": 0.05
    }
}


#############################################
# [추가] 장르 시드 및 템포 기대치 로드를 위한 함수들
#############################################

def normalize_genre(genre):
    """장르 문자열의 앞뒤 공백 제거 및 소문자화"""
    if not isinstance(genre, str):
        return ""
    return genre.strip().lower()

def load_genre_seeds():
    """genre_seeds.json 파일로부터 장르 시드 목록과 가중치 매핑을 불러옴"""
    try:
        with open('genre_seeds.json', encoding='utf-8') as f:
            data = json.load(f)
        mapping = {}
        for item in data.get("genres", []):
            if isinstance(item, dict):
                name = normalize_genre(item.get("name", ""))
                weights = item.get("weights", {})
                mapping[name] = weights
            else:
                mapping[normalize_genre(item)] = {
                    "미식가": 0.5,
                    "칠 가이": 0.5,
                    "BGM 마스터": 0.3,
                    "클러버": 0.3,
                    "사운드 실험가": 0.3,
                    "클래식 수호자": 0.3
                }
        return mapping
    except Exception as e:
        app.logger.exception("장르 시드 로드 실패")
        return {}

def load_tempo_expectations():
    """genre_seeds.json 파일에서 각 장르의 템포 기대치를 추출하여 매핑"""
    try:
        with open('genre_seeds.json', encoding='utf-8') as f:
            data = json.load(f)
        tempo_mapping = {}
        for item in data.get("genres", []):
            if isinstance(item, dict):
                name = normalize_genre(item.get("name", ""))
                # "tempo" 키가 있으면 가져오고, 없으면 기본값 100 BPM 사용
                tempo_mapping[name] = item.get("tempo", 100)
        return tempo_mapping
    except Exception as e:
        app.logger.exception("템포 기대치 로드 실패")
        return {}

# JSON 파일에서 장르 시드와 템포 기대치를 불러옴
GENRE_GROUP_WEIGHTS = load_genre_seeds()
if not GENRE_GROUP_WEIGHTS:
    GENRE_GROUP_WEIGHTS = {
        "indie": {"칠 가이": 0.3, "미식가": 0.7, "BGM 마스터": 0.4},
        "indie pop": {"칠 가이": 0.4, "미식가": 0.6, "BGM 마스터": 0.4},
        "alternative": {"미식가": 0.4, "BGM 마스터": 0.6, "클러버": 0.2},
        "experimental": {"사운드 실험가": 0.9, "미식가": 0.1, "칠 가이": 0.1},
        "lo-fi": {"칠 가이": 0.8, "BGM 마스터": 0.4, "미식가": 0.2},
        "ambient": {"칠 가이": 0.8, "BGM 마스터": 0.5},
        "pop": {"BGM 마스터": 0.5, "클러버": 0.3, "미식가": 0.2},
        "hip hop": {"클러버": 0.7, "사운드 실험가": 0.2},
        "rap": {"클러버": 0.7, "사운드 실험가": 0.2},
        "rock": {"클러버": 0.6, "미식가": 0.3, "BGM 마스터": 0.2},
    }

TEMPO_EXPECTATIONS = load_tempo_expectations()

#############################################
# [수정] 기존 함수들: compute_tempo_score, get_lyrics_sentiment, compute_genre_group_scores
#############################################

def compute_tempo_score(genres):
    """각 장르의 예상 BPM 값을 TEMPO_EXPECTATIONS에서 참조하여 평균 BPM을 계산한 후, 0~1 범위로 정규화하여 반환"""
    tempos = []
    for genre in genres:
        norm_genre = normalize_genre(genre)
        if norm_genre in TEMPO_EXPECTATIONS:
            tempos.append(TEMPO_EXPECTATIONS[norm_genre])
    if tempos:
        avg_bpm = sum(tempos) / len(tempos)
        # 예를 들어 BPM 범위를 60~140으로 가정하고 정규화 (실제 범위는 필요에 따라 조정)
        normalized_tempo = (avg_bpm - 60) / (140 - 60)
        return normalized_tempo
    return 0.5

def get_lyrics_sentiment(track_title, artist_name):
    try:
        song = genius.search_song(track_title, artist_name)
        if song and song.lyrics:
            sentiment_scores = sentiment_analyzer.polarity_scores(song.lyrics)
            return sentiment_scores["compound"]
        return 0
    except Exception as e:
        app.logger.exception(f"가사 감성 분석 중 오류: {track_title} - {artist_name}")
        return 0

def compute_genre_group_scores(genres):
    """
    입력된 장르 리스트를 순회하면서, 각 장르에 해당하는 그룹별 가중치를 누적한 후,
    각 그룹별 평균 가중치를 딕셔너리로 반환합니다.
    """
    group_scores = {
        "칠 가이": 0,
        "미식가": 0,
        "BGM 마스터": 0,
        "클러버": 0,
        "사운드 실험가": 0,
        "클래식 수호자": 0
    }
    total_keyword_matches = 0
    for genre in genres:
        norm_genre = normalize_genre(genre)
        if norm_genre in GENRE_GROUP_WEIGHTS:
            weights = GENRE_GROUP_WEIGHTS[norm_genre]
            for group, weight in weights.items():
                group_scores[group] += weight
            total_keyword_matches += 1
    if total_keyword_matches > 0:
        for group in group_scores:
            group_scores[group] /= total_keyword_matches
    return group_scores

#############################################
# Flask Routes & Endpoints
#############################################

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("q", "")
    if not query:
        return jsonify({"tracks": [], "artists": []})
    
    track_results = sp.search(q=query, type='track', limit=5)
    track_items = track_results.get('tracks', {}).get('items', [])
    tracks = []
    for item in track_items:
        album_images = item.get("album", {}).get("images", [])
        album_image = album_images[0]["url"] if album_images else ""
        tracks.append({
            "id": item["id"],
            "name": item["name"],
            "artist": ", ".join([artist["name"] for artist in item["artists"]]),
            "album_image": album_image,
            "preview_url": item.get("preview_url")
        })
    
    artist_results = sp.search(q=query, type='artist', limit=5)
    artist_items = artist_results.get('artists', {}).get('items', [])
    artists = []
    for item in artist_items:
        artist_images = item.get("images", [])
        artist_image = artist_images[0]["url"] if artist_images else ""
        artists.append({
            "id": item["id"],
            "name": item["name"],
            "followers": item["followers"]["total"],
            "image": artist_image
        })
    
    app.logger.info("Search query: %s, Tracks: %d, Artists: %d", query, len(tracks), len(artists))
    return jsonify({"tracks": tracks, "artists": artists})

@app.route("/artist_tracks", methods=["GET"])
def artist_tracks():
    artist_id = request.args.get("artist_id", "")
    if not artist_id:
        return jsonify([])
    
    top_tracks_data = sp.artist_top_tracks(artist_id, country='US')
    track_items = top_tracks_data.get('tracks', [])
    tracks = []
    for item in track_items:
        album_images = item.get("album", {}).get("images", [])
        album_image = album_images[0]["url"] if album_images else ""
        tracks.append({
            "id": item["id"],
            "name": item["name"],
            "artist": ", ".join([artist["name"] for artist in item["artists"]]),
            "album_image": album_image,
            "preview_url": item.get("preview_url")
        })
    return jsonify(tracks)

@app.route("/mbti", methods=["POST"])
def classify_music_taste():
    try:
        data = request.get_json()
        track_ids = data.get("track_ids", [])
        if not track_ids or len(track_ids) == 0:
            return jsonify({"group": "UNKNOWN", "explanation": "선택된 곡이 없습니다."})
        
        pop_list = []
        dur_list = []
        explicit_list = []
        sentiment_list = []
        tempo_list = []
        release_year_list = []
        genre_scores = []
        
        total_genre_group_scores = {
            "칠 가이": 0,
            "미식가": 0,
            "BGM 마스터": 0,
            "클러버": 0,
            "사운드 실험가": 0,
            "클래식 수호자": 0
        }
        total_decade_group_scores = {
            "칠 가이": 0,
            "미식가": 0,
            "BGM 마스터": 0,
            "클러버": 0,
            "사운드 실험가": 0,
            "클래식 수호자": 0
        }
        
        valid_tracks = 0
        artist_genre_cache = {}
        
        for tid in track_ids:
            try:
                track_detail = sp.track(tid)
                pop_list.append(track_detail.get("popularity", 0))
                dur_list.append(track_detail.get("duration_ms", 0))
                explicit_list.append(1 if track_detail.get("explicit", False) else 0)
                
                album = track_detail.get("album", {})
                release_date = album.get("release_date", "2020")
                year = int(release_date.split("-")[0])
                release_year_list.append(year)
                decade = f"{(year // 10) * 10}s"
                if decade not in DECADE_GROUP_WEIGHTS:
                    decade = "2000s"
                decade_weights = DECADE_GROUP_WEIGHTS[decade]
                for group, weight in decade_weights.items():
                    total_decade_group_scores[group] += weight
                
                artists = track_detail.get("artists", [])
                primary_artist_name = ""
                genres = []
                tempo_score = 0
                if artists:
                    primary_artist = artists[0]
                    primary_artist_id = primary_artist.get("id")
                    primary_artist_name = primary_artist.get("name", "")
                    if primary_artist_id:
                        if primary_artist_id in artist_genre_cache:
                            genres = artist_genre_cache[primary_artist_id]
                        else:
                            artist_detail = sp.artist(primary_artist_id)
                            genres = artist_detail.get("genres", [])
                            genres = [normalize_genre(g) for g in genres]
                            artist_genre_cache[primary_artist_id] = genres
                        group_scores = compute_genre_group_scores(genres)
                        # genre_scores에 각 그룹별 평균 가중치의 단순 평균 값을 저장 (종합 지표로 활용)
                        genre_scores.append(np.mean(list(group_scores.values())))
                        tempo_score = compute_tempo_score(genres)
                        for group in total_genre_group_scores:
                            total_genre_group_scores[group] += group_scores.get(group, 0)
                tempo_list.append(tempo_score)
                
                track_title = track_detail.get("name", "")
                lyrics_sentiment = get_lyrics_sentiment(track_title, primary_artist_name)
                sentiment_list.append(lyrics_sentiment)
                
                valid_tracks += 1
            except Exception as e:
                app.logger.exception(f"트랙 처리 중 오류 발생: {tid}")
                continue
        
        if valid_tracks == 0:
            return jsonify({"group": "UNKNOWN", "explanation": "트랙 메타데이터를 가져올 수 없습니다."})
        
        pop_arr = np.array(pop_list)
        dur_arr = np.array(dur_list)
        explicit_arr = np.array(explicit_list)
        sentiment_arr = np.array(sentiment_list)
        tempo_arr = np.array(tempo_list)
        
        if release_year_list:
            release_year_arr = np.array(release_year_list)
            release_year_norm = (release_year_arr - 1950) / (2023 - 1950)
            avg_release_year_norm = release_year_norm.mean()
            release_year_diversity = np.std(release_year_norm)
        else:
            avg_release_year_norm = 0.5
            release_year_diversity = 0.5
        
        pop_norm = pop_arr / 100.0
        dur_norm = np.clip((dur_arr - 60000) / 360000.0, 0, 1)
        explicit_norm = explicit_arr.mean()
        sentiment_norm = ((sentiment_arr.mean()) + 1) / 2.0
        tempo_norm = tempo_arr.mean()
        
        if genre_scores:
            genre_diversity = np.std(genre_scores)
            genre_diversity_norm = np.clip(genre_diversity / 0.5, 0, 1)
        else:
            genre_diversity_norm = 0.5
        
        avg_genre_group_scores = {group: total_genre_group_scores[group] / valid_tracks 
                                  for group in total_genre_group_scores}
        avg_decade_group_scores = {group: total_decade_group_scores[group] / valid_tracks 
                                  for group in total_decade_group_scores}
        
        alpha = 0.6
        beta = 1.0  # 미식가 그룹에 대해 장르 다양성 반영 보정 상수
        final_group_scores = {}
        for group in total_genre_group_scores:
            score = alpha * avg_genre_group_scores[group] + (1 - alpha) * avg_decade_group_scores[group]
            if group == "미식가":
                score += beta * genre_diversity_norm
            final_group_scores[group] = score
        
        predicted_group = max(final_group_scores, key=final_group_scores.get)
        if predicted_group == "미식가" and genre_diversity_norm < 0.2:
            filtered_scores = {g: s for g, s in final_group_scores.items() if g != "미식가"}
            predicted_group = max(filtered_scores, key=filtered_scores.get)
        
        group = "기타"
        explanation_details = (
            f"(pop: {pop_norm.mean():.2f}, dur: {dur_norm.mean():.2f}, "
            f"explicit: {explicit_norm:.2f}, tempo: {tempo_norm:.2f}, sentiment: {sentiment_norm:.2f}, "
            f"release_year_avg: {avg_release_year_norm:.2f}, release_year_diversity: {release_year_diversity:.2f}, "
            f"genre_diversity: {genre_diversity_norm:.2f}, 장르 그룹: {avg_genre_group_scores}, "
            f"데케이드 그룹: {avg_decade_group_scores})"
        )
        
        if tempo_norm < 0.6 and sentiment_norm >= 0.2 and final_group_scores.get("칠 가이", 0) >= 0.25:
            group = "칠 가이"
        elif pop_norm.mean() < 0.4 and final_group_scores.get("미식가", 0) >= 0.3 and genre_diversity_norm >= 0.4:
            group = "미식가"
        elif (0.5 <= pop_norm.mean() <= 0.7 and 0.4 <= dur_norm.mean() <= 0.6 and 0.45 <= tempo_norm <= 0.55 
              and explicit_norm < 0.1 and final_group_scores.get("BGM 마스터", 0) >= 0.4):
            group = "BGM 마스터"
        elif pop_norm.mean() >= 0.7 and dur_norm.mean() < 0.4 and tempo_norm >= 0.8 and explicit_norm >= 0.3 and final_group_scores.get("클러버", 0) >= 0.5:
            group = "클러버"
        elif pop_norm.mean() < 0.4 and tempo_norm >= 0.6 and 0.2 <= explicit_norm <= 0.4 and final_group_scores.get("사운드 실험가", 0) >= 0.7:
            group = "사운드 실험가"
        elif (0.4 <= pop_norm.mean() <= 0.6 and dur_norm.mean() >= 0.6 and tempo_norm < 0.4 and explicit_norm < 0.1 and 
              avg_release_year_norm < 0.3 and release_year_diversity < 0.2 and final_group_scores.get("클래식 수호자", 0) >= 0.7):
            group = "클래식 수호자"
        else:
            group = predicted_group
        
        explanation = f"당신의 음악 지표: {explanation_details}\n이 기준에 따라, 당신은 '{group}'으로 분류됩니다!"
        return jsonify({"group": group, "explanation": explanation})
    except Exception as e:
        app.logger.exception("음악 취향 분류 중 오류 발생")
        return jsonify({"group": "UNKNOWN", "explanation": "분류에 실패했습니다."}), 500

@app.route("/result", methods=["GET"])
def result():
    group = request.args.get("group", "UNKNOWN")
    explanation = request.args.get("explanation", "")
    images = {
        "칠 가이": "static/images/chill_guy.png",
        "미식가": "static/images/gourmet.png",
        "BGM 마스터": "static/images/bgm_master.png",
        "클러버": "static/images/clubber.png",
        "사운드 실험가": "static/images/sound_explorer.png",
        "클래식 수호자": "static/images/classic_guardian.png"
    }
    image_url = images.get(group, "static/images/default.png")
    return render_template("result.html", group=group, explanation=explanation, image_url=image_url)

if __name__ == "__main__":
    app.run(debug=True)
