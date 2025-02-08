from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import logging
import requests
import re
import numpy as np

# 가사 가져오기 및 감성 분석용 라이브러리 (TextBlob 대신 VADER 사용)
import nltk
nltk.download('vader_lexicon')
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import lyricsgenius

# .env 파일의 환경 변수 로드
load_dotenv()

app = Flask(__name__)

# 환경 변수에서 Spotify 클라이언트 ID와 Secret, Genius 토큰 가져오기
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
# 1. 장르 가중치 및 템포 기대치 사전 정의
#############################################

# GENRE_GROUP_WEIGHTS를 확장하여 서브 장르도 반영
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
    "alt rock": {"클러버": 0.65, "미식가": 0.25, "BGM 마스터": 0.15},
    "classical": {"클래식 수호자": 0.9, "칠 가이": 0.3},
    "jazz": {"미식가": 0.7, "칠 가이": 0.3, "BGM 마스터": 0.3},
    "electronic": {"클러버": 0.6, "사운드 실험가": 0.4, "BGM 마스터": 0.2},
    "edm": {"클러버": 0.8, "사운드 실험가": 0.3, "BGM 마스터": 0.2},
    "country": {"클래식 수호자": 0.6, "칠 가이": 0.3, "미식가": 0.2},
}

# DECADE_GROUP_WEIGHTS: 발매 연도(데케이드)별 음악적 트렌드를 반영하는 가중치
DECADE_GROUP_WEIGHTS = {
    "1960s": {"칠 가이": 0.2, "미식가": 0.3, "BGM 마스터": 0.1, "클러버": 0.1, "사운드 실험가": 0.1, "클래식 수호자": 0.2},
    "1970s": {"칠 가이": 0.2, "미식가": 0.3, "BGM 마스터": 0.1, "클러버": 0.1, "사운드 실험가": 0.1, "클래식 수호자": 0.2},
    "1980s": {"칠 가이": 0.25, "미식가": 0.25, "BGM 마스터": 0.15, "클러버": 0.15, "사운드 실험가": 0.1, "클래식 수호자": 0.1},
    "1990s": {"칠 가이": 0.3, "미식가": 0.2, "BGM 마스터": 0.2, "클러버": 0.1, "사운드 실험가": 0.1, "클래식 수호자": 0.1},
    "2000s": {"칠 가이": 0.3, "미식가": 0.2, "BGM 마스터": 0.1, "클러버": 0.2, "사운드 실험가": 0.1, "클래식 수호자": 0.1},
    "2010s": {"칠 가이": 0.3, "미식가": 0.2, "BGM 마스터": 0.1, "클러버": 0.2, "사운드 실험가": 0.1, "클래식 수호자": 0.1},
    "2020s": {"칠 가이": 0.3, "미식가": 0.2, "BGM 마스터": 0.1, "클러버": 0.2, "사운드 실험가": 0.1, "클래식 수호자": 0.1},
}

# 기존 단일 장르 점수 계산 함수 (장르 다양성 지표용)
def compute_genre_score(genres):
    scores = []
    for genre in genres:
        for key, weight in GENRE_GROUP_WEIGHTS.items():
            if key in genre:
                scores.append(weight.get("BGM 마스터", 0.5))  # 예시로 BGM 마스터 가중치 사용
                break
    if scores:
        return sum(scores) / len(scores)
    return 0.5

def compute_tempo_score(genres):
    # 현재는 간단한 예시로 0.5 반환 (필요시 장르별 평균 템포 참고 자료 활용 가능)
    scores = [0.5 for _ in genres]
    if scores:
        return sum(scores) / len(scores)
    return 0.5

def get_lyrics_sentiment(track_title, artist_name):
    """
    Genius에서 가사를 검색 후, VADER를 사용해 감성 점수(compound, -1 ~ 1)를 반환.
    가사를 찾지 못하면 0 반환.
    """
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
    아티스트의 장르 목록(소문자 변환된 상태)을 기반으로,
    각 그룹별 기여도를 누적 후 매칭된 키워드 수로 평균화한 dict 반환.
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
        for key, weights in GENRE_GROUP_WEIGHTS.items():
            if key in genre:
                for group, weight in weights.items():
                    group_scores[group] += weight
                total_keyword_matches += 1
    if total_keyword_matches > 0:
        for group in group_scores:
            group_scores[group] /= total_keyword_matches
    return group_scores

#############################################
# 기본 라우트 및 검색/아티스트 트랙 엔드포인트
#############################################
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("q", "")
    if not query:
        return jsonify({"tracks": [], "artists": []})
    
    # 트랙 검색 (limit 5)
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
            "album_image": album_image
        })
    
    # 아티스트 검색 (limit 5)
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
    
    return jsonify({"tracks": tracks, "artists": artists})

@app.route("/artist_tracks", methods=["GET"])
def artist_tracks():
    artist_id = request.args.get("artist_id", "")
    if not artist_id:
        return jsonify([])
    
    top_tracks_data = sp.artist_top_tracks(artist_id, country='US')
    track_items = top_tracks_data.get("tracks", [])
    tracks = []
    for item in track_items:
        album_images = item.get("album", {}).get("images", [])
        album_image = album_images[0]["url"] if album_images else ""
        tracks.append({
            "id": item["id"],
            "name": item["name"],
            "artist": ", ".join([artist["name"] for artist in item["artists"]]),
            "album_image": album_image
        })
    return jsonify(tracks)

#############################################
# 음악 취향 그룹 분류 엔드포인트 (6개 그룹)
#############################################
@app.route("/mbti", methods=["POST"])
def classify_music_taste():
    """
    선택한 5곡의 Spotify 메타데이터를 기반으로,
    다음 6개 그룹 중 하나로 분류합니다:
      - 칠 가이
      - 미식가
      - BGM 마스터
      - 클러버
      - 사운드 실험가
      - 클래식 수호자
      
    고려 피처:
      • 인기도 (pop_norm)
      • 재생 시간 (dur_norm)
      • explicit 비율 (explicit_norm)
      • 템포 (tempo_norm)
      • 가사 감성 (sentiment_norm)
      • 발매 연도 평균 (avg_release_year_norm) 및 다양성 (release_year_diversity)
      • 장르 다양성 (genre_diversity_norm)
      • 장르 기반 그룹 기여도와 발매 연도(데케이드) 트렌드 반영
    """
    try:
        data = request.get_json()
        track_ids = data.get("track_ids", [])
        if not track_ids or len(track_ids) == 0:
            return jsonify({"group": "UNKNOWN", "explanation": "선택된 곡이 없습니다."})
        
        pop_list = []         # 인기도
        dur_list = []         # 재생 시간 (ms)
        explicit_list = []    # explicit 여부 (0 또는 1)
        sentiment_list = []   # 가사 감성 (-1 ~ 1)
        tempo_list = []       # 템포 기대치 (0~1)
        release_year_list = []  # 발매 연도
        genre_scores = []       # 단일 장르 점수 (장르 다양성 지표용)
        
        # 그룹별 누적 장르 기여도
        total_genre_group_scores = {
            "칠 가이": 0, 
            "미식가": 0, 
            "BGM 마스터": 0, 
            "클러버": 0, 
            "사운드 실험가": 0, 
            "클래식 수호자": 0
        }
        # 그룹별 누적 발매 연도(데케이드) 가중치
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
                
                # 발매 연도 추출 및 데케이드 가중치 반영
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
                
                # 아티스트 장르 정보 (첫 번째 아티스트 기준)
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
                            genres = [g.lower() for g in genres]
                            artist_genre_cache[primary_artist_id] = genres
                        # 단일 장르 점수 (장르 다양성 계산에 사용)
                        single_genre_score = compute_genre_score(genres)
                        genre_scores.append(single_genre_score)
                        # 템포 기대치 계산
                        tempo_score = compute_tempo_score(genres)
                        # 장르 기반 그룹 기여도 계산
                        group_scores = compute_genre_group_scores(genres)
                        for group in total_genre_group_scores:
                            total_genre_group_scores[group] += group_scores.get(group, 0)
                tempo_list.append(tempo_score)
                
                # 가사 감성 분석 (VADER 사용)
                track_title = track_detail.get("name", "")
                lyrics_sentiment = get_lyrics_sentiment(track_title, primary_artist_name)
                sentiment_list.append(lyrics_sentiment)
                
                valid_tracks += 1
            except Exception as e:
                app.logger.exception(f"트랙 처리 중 오류 발생: {tid}")
                continue
        
        if valid_tracks == 0:
            return jsonify({"group": "UNKNOWN", "explanation": "트랙 메타데이터를 가져올 수 없습니다."})
        
        # numpy 배열로 변환
        pop_arr = np.array(pop_list)
        dur_arr = np.array(dur_list)
        explicit_arr = np.array(explicit_list)
        sentiment_arr = np.array(sentiment_list)
        tempo_arr = np.array(tempo_list)
        
        # 발매 연도 정규화 (예: 1950 ~ 2023)
        if release_year_list:
            release_year_arr = np.array(release_year_list)
            release_year_norm = (release_year_arr - 1950) / (2023 - 1950)
            avg_release_year_norm = release_year_norm.mean()
            release_year_diversity = np.std(release_year_norm)
        else:
            avg_release_year_norm = 0.5
            release_year_diversity = 0.5
        
        # 기본 메타데이터 정규화
        pop_norm = pop_arr / 100.0
        dur_norm = np.clip((dur_arr - 60000) / 360000.0, 0, 1)
        explicit_norm = explicit_arr.mean()
        sentiment_norm = ((sentiment_arr.mean()) + 1) / 2.0
        tempo_norm = tempo_arr.mean()
        
        # 장르 다양성 지표: 단일 장르 점수의 표준편차 (최대 다양성 0.5 기준)
        if genre_scores:
            genre_diversity = np.std(genre_scores)
            genre_diversity_norm = np.clip(genre_diversity / 0.5, 0, 1)
        else:
            genre_diversity_norm = 0.5
        
        # 각 그룹별 평균 장르 기반 기여도 및 데케이드 기반 기여도
        avg_genre_group_scores = {group: total_genre_group_scores[group] / valid_tracks 
                                  for group in total_genre_group_scores}
        avg_decade_group_scores = {group: total_decade_group_scores[group] / valid_tracks 
                                  for group in total_decade_group_scores}
        # 최종 그룹 점수: 장르 기반 점수와 데케이드 기반 점수에 가중치를 부여하여 결합 (예: α=0.6)
        alpha = 0.6
        beta = 1.0  # 장르 다양성을 직접 반영하는 보정 상수
        final_group_scores = {}
        for group in total_genre_group_scores:
            score = alpha * avg_genre_group_scores[group] + (1 - alpha) * avg_decade_group_scores[group]
            # 미식가 그룹에 대해 genre_diversity_norm의 기여를 직접 반영
            if group == "미식가":
                score += beta * genre_diversity_norm
            final_group_scores[group] = score
        
        # predicted_group 계산 후, 만약 predicted_group이 미식가인데 genre_diversity_norm이 낮으면 미식가 제외
        predicted_group = max(final_group_scores, key=final_group_scores.get)
        if predicted_group == "미식가" and genre_diversity_norm < 0.4:
            filtered_scores = {g: s for g, s in final_group_scores.items() if g != "미식가"}
            predicted_group = max(filtered_scores, key=filtered_scores.get)
        
        #############################################
        # 통합 결정 조건: 여러 피처 및 그룹 점수를 고려하여 분류
        #############################################
        group = "기타"
        explanation_details = (
            f"(pop: {pop_norm.mean():.2f}, dur: {dur_norm.mean():.2f}, "
            f"explicit: {explicit_norm:.2f}, tempo: {tempo_norm:.2f}, sentiment: {sentiment_norm:.2f}, "
            f"release_year_avg: {avg_release_year_norm:.2f}, release_year_diversity: {release_year_diversity:.2f}, "
            f"genre_diversity: {genre_diversity_norm:.2f}, 장르 그룹: {avg_genre_group_scores}, "
            f"데케이드 그룹: {avg_decade_group_scores})"
        )
        
        # 수정된 조건:
        # 칠 가이: 템포가 낮고 감성 점수가 높으면 칠 가이로 분류
        if tempo_norm < 0.6 and sentiment_norm >= 0.2 and final_group_scores.get("칠 가이", 0) >= 0.25:
            group = "칠 가이"
        # 미식가: 인기도가 낮고, genre_diversity가 일정 수준 이상(>=0.4)이며, 미식가 점수가 일정 이상일 때
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

#############################################
# 결과 페이지 라우트
#############################################
@app.route("/result", methods=["GET"])
def result():
    group = request.args.get("group", "UNKNOWN")
    explanation = request.args.get("explanation", "")

    # 그룹별 이미지 매핑
    images = {
        "칠 가이": "static/images/chill_guy.png",
        "미식가": "static/images/gourmet.png",
        "BGM 마스터": "static/images/bgm_master.png",
        "클러버": "static/images/clubber.png",
        "사운드 실험가": "static/images/sound_explorer.png",
        "클래식 수호자": "static/images/classic_guardian.png",
    }

    # 그룹에 맞는 이미지 URL 가져오기
    image_url = images.get(group, "static/images/default.png")

    return render_template(
        "result.html",
        group=group,
        explanation=explanation,
        image_url=image_url
    )

if __name__ == "__main__":
    app.run(debug=True)
