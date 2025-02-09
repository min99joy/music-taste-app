$(document).ready(function () {
    // 전역 변수: 선택된 트랙 ID들을 저장하는 배열
    let selectedTrackIds = [];
    
    const $input = $("#search-input");
    const $suggestions = $("#suggestions"); // 전체 자동완성 컨테이너
    const $trackSuggestions = $("#track-suggestions");
    const $artistSuggestions = $("#artist-suggestions");
    const $artistTracksSection = $("#artist-tracks-section"); // 아티스트의 곡 리스트
    const $artistTracks = $("#artist-tracks");
    const $selectedList = $("#selected-list");

    // 검색창 입력 시 AJAX 호출하여 트랙, 아티스트 결과 업데이트
    $input.on("input", function () {
        const query = $input.val().trim();
        if (query.length < 2) {
            resetSuggestions(); // 자동완성 창 숨기기
            return;
        }
        $.getJSON("/search", { q: query }, function (data) {
            // 트랙 및 아티스트 결과 업데이트
            updateTrackSuggestions(data.tracks);
            updateArtistSuggestions(data.artists);

            // 검색 결과가 있으면 보이도록 설정
            $suggestions.addClass("visible").css("display", "flex");
            $artistTracksSection.removeClass("visible");
        });
    });

    // 동적으로 트랙 결과 업데이트
    function updateTrackSuggestions(tracks) {
        $trackSuggestions.empty();
        if (tracks && tracks.length > 0) {
            $trackSuggestions.append("<h3>곡 검색 결과</h3>");
            tracks.forEach(function (item) {
                const imgTag = item.album_image
                    ? `<img src="${item.album_image}" alt="앨범 커버" style="width:40px;height:40px;vertical-align:middle;margin-right:8px;">`
                    : "";
                const displayText = `${imgTag}${item.name} - ${item.artist}`;
                const $div = $("<div class='suggestion'></div>").html(displayText);
                $div.data("item", { type: "track", data: item });
                $trackSuggestions.append($div);
            });
        } else {
            $trackSuggestions.append("<div>검색된 곡이 없습니다.</div>");
        }
    }

    // 동적으로 아티스트 결과 업데이트
    function updateArtistSuggestions(artists) {
        $artistSuggestions.empty();
        if (artists && artists.length > 0) {
            $artistSuggestions.append("<h3>가수 검색 결과</h3>");
            artists.forEach(function (item) {
                const imgTag = item.image
                    ? `<img src="${item.image}" alt="아티스트 사진" style="width:40px;height:40px;vertical-align:middle;margin-right:8px;">`
                    : "";
                const displayText = `${imgTag}${item.name} (${item.followers} followers)`;
                const $div = $("<div class='suggestion'></div>").html(displayText);
                $div.data("item", { type: "artist", data: item });
                $artistSuggestions.append($div);
            });
        } else {
            $artistSuggestions.append("<div>검색된 가수가 없습니다.</div>");
        }
    }

    // 클릭 이벤트: 트랙 결과(직접 선택)
    $(document).on("click", "#track-suggestions .suggestion", function () {
        const itemObj = $(this).data("item");
        if (itemObj && itemObj.type === "track") {
            addSelectedTrack(itemObj.data);
            resetSuggestions();
            $input.val("");
        }
    });

    // 클릭 이벤트: 아티스트 결과 (선택 시 아티스트의 곡 목록 요청)
    $(document).on("click", "#artist-suggestions .suggestion", function () {
        const itemObj = $(this).data("item");
        if (itemObj && itemObj.type === "artist") {
            fetchArtistTracks(itemObj.data.id, itemObj.data.name);
            $suggestions.css("display", "none"); // 자동완성 창 숨기기
        }
    });

    // 클릭 이벤트: 아티스트 트랙 영역에서 곡 선택
    $(document).on("click", "#artist-tracks .suggestion", function () {
        const itemObj = $(this).data("item");
        if (itemObj && itemObj.type === "track") {
            addSelectedTrack(itemObj.data);
            $artistTracksSection.hide();
            $artistTracks.empty();
            $input.val("");
        }
    });

    // 함수: 아티스트의 곡 목록 가져오기
    function fetchArtistTracks(artistId, artistName) {
        $.getJSON("/artist_tracks", { artist_id: artistId }, function (tracks) {
            $artistTracks.empty();
            if (tracks && tracks.length > 0) {
                $artistTracks.append(`<h3>${artistName}의 곡들</h3>`);
                tracks.forEach(function (track) {
                    const imgTag = track.album_image
                        ? `<img src="${track.album_image}" alt="앨범 커버" style="width:40px;height:40px;vertical-align:middle;margin-right:8px;">`
                        : "";
                    const displayText = `${imgTag}${track.name} - ${track.artist}`;
                    const $div = $("<div class='suggestion'></div>").html(displayText);
                    $div.data("item", { type: "track", data: track });
                    $artistTracks.append($div);
                });

                // 아티스트 곡 리스트 창을 자동완성 창과 동일한 레이아웃으로 표시
                $artistTracksSection
                .removeAttr("style") // 기존의 display: none; 제거
                .addClass("visible artist-tracks-style"); // 올바른 클래스 추가
            } else {
                $artistTracks.append("<div>해당 아티스트의 곡 정보를 찾지 못했습니다.</div>");
            }
        });
    }

    function getPreviewUrlFromiTunes(trackName, artistName, callback) {
        const iTunesUrl = `https://itunes.apple.com/search?term=${encodeURIComponent(trackName + " " + artistName)}&entity=musicTrack&limit=1`;
    
        fetch(iTunesUrl)
            .then(response => response.json())
            .then(data => {
                if (data.resultCount > 0) {
                    const previewUrl = data.results[0].previewUrl || null;
                    callback(previewUrl);
                } else {
                    callback(null);
                }
            })
            .catch(error => {
                console.error("iTunes API Error:", error);
                callback(null);
            });
    }    

    // 함수: 선택된 트랙 추가
    function addSelectedTrack(trackData) {
        // 최대 5곡 제한
        if (selectedTrackIds.length >= 5) {
            alert("이미 5곡이 선택되었습니다.");
            return;
        }

        // 선택된 트랙 ID를 배열에 추가
        selectedTrackIds.push(trackData.id);

        const previewUrl = trackData.preview_url ? trackData.preview_url : null;

        getPreviewUrlFromiTunes(trackData.name, trackData.artist, function (itunesPreviewUrl) {
            const finalPreviewUrl = itunesPreviewUrl || trackData.preview_url; // iTunes URL 우선 사용

            // 곡 리스트 항목 생성
            const $li = $(`
                <li data-preview-url="${finalPreviewUrl}">
                    <img src="${trackData.album_image}" alt="앨범 커버">
                    <div class="progress-container">
                        <div class="progress-bar"></div>  <!-- 🔥 여기가 초록색으로 차오를 부분 -->
                    </div>
                    <div class="track-info">${trackData.name}</div>
                    <div class="play-button">
                        <i class="fas fa-play"></i> <!-- FontAwesome 아이콘 사용 -->
                    </div>
                </li>
            `);

            // 선택된 리스트에 추가
            $("#selected-list").append($li);

            // 선택된 곡이 5곡일 경우 자동 제출
            if (selectedTrackIds.length === 5) {
                submitSelectedTracks();
            }
        });
    }

// 오디오 재생 및 진행 바 업데이트를 위한 함수 정의
function updateProgress() {
    // 오디오의 현재 재생 시간 사용
    let currentTime = currentAudio.currentTime;
    let progressPercent = (currentTime / duration) * 100;
    
    const trackCardWidth = $li.width(); // 트랙 카드 전체 너비
    const albumCoverWidth = 60; // 앨범 커버 + 여백
    const progressWidth = trackCardWidth - albumCoverWidth;
    
    $progressBar.css({
        "left": `${albumCoverWidth}px`,
        "width": `${(progressPercent / 100) * progressWidth}px`,
        "max-width": `${progressWidth}px`
    });
    
    // 재생 중이면 requestAnimationFrame을 통해 다음 프레임 업데이트
    if (currentTime < duration) {
        requestAnimationFrame(updateProgress);
    } else {
        // 재생이 끝나면 진행 바 리셋
        $progressBar.css("width", "0%");
    }
}

// play-button 클릭 이벤트 내에서
$(document).on("click", ".play-button", function () {
    const $li = $(this).closest("li");
    const previewUrl = $li.data("preview-url");
    const $progressBar = $li.find(".progress-bar");

    if (!previewUrl) {
        alert("이 곡은 미리 듣기를 지원하지 않습니다.");
        return;
    }

    // 기존 재생 중인 오디오가 있으면 정지 및 리셋
    if (currentAudio) {
        currentAudio.pause();
        $(".progress-bar").css("width", "0%");
    }

    // 새로운 오디오 객체 생성 및 재생
    currentAudio = new Audio(previewUrl);
    currentAudio.play();

    // iTunes 미리 듣기 기본 길이 (30초)
    let duration = 30;

    // requestAnimationFrame을 사용하여 진행 바 업데이트 시작
    requestAnimationFrame(updateProgress);
});


    // 함수: 선택한 곡 제출
    function submitSelectedTracks() {
        $.ajax({
            url: "/mbti",
            type: "POST",
            contentType: "application/json",
            data: JSON.stringify({ track_ids: selectedTrackIds }),
            success: function (response) {
                const resultUrl = `/result?group=${encodeURIComponent(response.group)}&explanation=${encodeURIComponent(response.explanation)}`;
                window.location.href = resultUrl;
            },
            error: function () {
                alert("MBTI 분류 중 오류가 발생했습니다. 다시 시도해주세요.");
            },
        });
    }

    // 함수: 검색 및 제안 초기화
    function resetSuggestions() {
        $suggestions.css("display", "none");
        $trackSuggestions.empty();
        $artistSuggestions.empty();
    }
});
