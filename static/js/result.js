// result.js
document.addEventListener("DOMContentLoaded", function () {
    // 결과 페이지에서만 실행할 코드
    const showAnalysisBtn = document.getElementById('show-analysis');
    if (showAnalysisBtn) {
      showAnalysisBtn.addEventListener('click', function () {
        // 모달 열기 및 차트 초기화 코드
        const modal = document.getElementById('detailed-analysis');
        modal.style.display = 'block';
        setTimeout(function() {
          const analysisDataStr = localStorage.getItem("analysisData");
          if (analysisDataStr) {
            const analysisData = JSON.parse(analysisDataStr);
            const groupScores = analysisData.final_group_scores;
            const labels = Object.keys(groupScores);
            const dataValues = Object.values(groupScores);
            const canvasElem = document.getElementById('analysisChart');
            if (canvasElem) {
              const ctx = canvasElem.getContext('2d');
              new Chart(ctx, {
                type: 'bar',
                data: {
                  labels: labels,
                  datasets: [{
                    label: '최종 그룹 점수',
                    data: dataValues,
                    backgroundColor: [
                      '#1DB954', '#4CAF50', '#FFC107', '#E91E63', '#9C27B0', '#3F51B5'
                    ],
                  }]
                },
                options: {
                  responsive: true,
                  plugins: {
                    legend: { position: 'top' },
                    title: { display: true, text: '음악 취향 분석 결과' }
                  }
                },
              });
            }
          } else {
            alert("분석 데이터를 찾을 수 없습니다.");
          }
        }, 300); // 충분한 지연 시간을 줍니다.
      });
    }
    
    const closeAnalysisBtn = document.getElementById('close-analysis');
    if (closeAnalysisBtn) {
      closeAnalysisBtn.addEventListener('click', function () {
        document.getElementById('detailed-analysis').style.display = 'none';
      });
    }
    
    // 공유 버튼 등도 result.js 내부에서 처리
    const shareBtn = document.getElementById('share-btn');
    if (shareBtn) {
      shareBtn.addEventListener('click', function(e) {
        e.preventDefault();
        const shareUrl = window.location.href;
        if (navigator.share) {
        // Web Share API 지원 시 (주로 모바일)
          navigator.share({
            title: '음악 취향 분석 결과',
            text: '내 음악 취향을 확인해보세요!',
            url: shareUrl
          })
          .then(() => console.log('공유 성공'))
          .catch((error) => console.error('공유 실패', error));
        } else if (navigator.clipboard) {
        // 지원되지 않을 경우 클립보드에 URL 복사
          navigator.clipboard.writeText(shareUrl).then(() => {
            alert("결과 페이지 URL이 복사되었습니다!");
          }).catch(err => {
            alert("공유에 실패했습니다. 직접 URL을 복사해주세요.");
          });
        } else {
          alert("이 브라우저는 공유 기능을 지원하지 않습니다.");
        }
      });
    }
  });
  