async function updatePrefectures() {
    const regionSelect = document.getElementById('region');
    const prefectureSelect = document.getElementById('prefecture');
    const feedTypeSelect = document.getElementById('feed_type');
    const selectedRegion = regionSelect.value;

    // 選択された地域が空の場合は、都道府県セレクトボックスをクリアして終了
    if (!selectedRegion) {
        prefectureSelect.innerHTML = '<option value="">-- 選択してください --</option>';
        return;
    }

    // /get_prefectures エンドポイントから都道府県のリストを取得
    const response = await fetch(`/get_prefectures?region=${encodeURIComponent(selectedRegion)}`);
    const prefectures = await response.json();

    // 都道府県セレクトボックスのオプションを更新
    let options = '<option value="">-- 選択してください --</option>';
    for (const prefecture of prefectures) {
        options += `<option value="${prefecture}">${prefecture}</option>`;
    }
    prefectureSelect.innerHTML = options;

    // クッキーに保存されている都道府県を選択状態にする (存在する場合)
    const selectedPrefecture = getCookie('selected_prefecture');
    if (selectedPrefecture) {
        prefectureSelect.value = decodeURIComponent(selectedPrefecture); // デコード
    }

    // クッキーに保存されている feed_type を選択状態にする (存在する場合)
    const selectedFeedType = getCookie('selected_feed_type');
    if (selectedFeedType) {
        feedTypeSelect.value = selectedFeedType;
    }
}

// クッキーから値を取得する関数
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

// クッキーに値を設定する関数 (必要に応じてエスケープ処理を追加)
function setCookie(name, value) {
    document.cookie = `${name}=${encodeURIComponent(value)};path=/`;
  }

  // ページ読み込み時の処理
document.addEventListener('DOMContentLoaded', () => {
    const regionSelect = document.getElementById('region');
    const feedTypeSelect = document.getElementById('feed_type');

    // クッキーから selected_region を取得し、region セレクトボックスの値を設定
    const selectedRegion = getCookie('selected_region');
    if (selectedRegion) {
        regionSelect.value = decodeURIComponent(selectedRegion);
    }

    // updatePrefectures は region が選択されている場合のみ実行
    if (selectedRegion) {
        updatePrefectures();
    }

    // selected_feed_type をクッキーから取得し、該当する項目を選択状態にする
    const selectedFeedType = getCookie('selected_feed_type');
    if (selectedFeedType) {
        feedTypeSelect.value = selectedFeedType;
    } else {
        // クッキーに feed_type がない場合の初期値を設定
        feedTypeSelect.value = "extra";
        setCookie('selected_feed_type', 'extra');
    }
    updatePrefectures();

    // 文字サイズ変更
    const fontIncreaseBtn = document.getElementById('font-increase');
    const fontDecreaseBtn = document.getElementById('font-decrease');
    let currentFontSize = parseFloat(window.getComputedStyle(document.body).fontSize) || 16;
    
    fontIncreaseBtn.addEventListener('click', () => {
        currentFontSize = Math.min(currentFontSize + 2, 36);
        document.body.style.fontSize = currentFontSize + 'px';
    });
    
    fontDecreaseBtn.addEventListener('click', () => {
        currentFontSize = Math.max(currentFontSize - 2, 10);
        document.body.style.fontSize = currentFontSize + 'px';
    });
    
    // テーマ切替
    const themeToggleBtn = document.getElementById('theme-toggle');
    themeToggleBtn.addEventListener('click', () => {
        document.body.classList.toggle('dark-mode');
    });

    // フォーム送信時のイベントハンドラーを追加
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const formData = new FormData(form);
            const region = formData.get('region');
            const prefecture = formData.get('prefecture');
            const feedType = formData.get('feed_type');

            // クッキーに選択値を保存
            setCookie('selected_region', region);
            setCookie('selected_prefecture', prefecture);
            setCookie('selected_feed_type', feedType);

            const encodedRegion = encodeURIComponent(region);
            const encodedPrefecture = encodeURIComponent(prefecture);

            // 非同期でRSSフィードのHTMLを取得し、div#feed-data に表示
            const rssUrl = `/rss/${feedType}?region=${encodedRegion}&prefecture=${encodedPrefecture}`;
            try {
                const response = await fetch(rssUrl, {
                    credentials: 'same-origin'
                });
                if (response.ok) {
                    const htmlContent = await response.text();
                    document.getElementById('feed-data').innerHTML = htmlContent;
                } else {
                    document.getElementById('feed-data').innerHTML = `<p>フィードの取得に失敗しました。</p>`;
                }
            } catch (error) {
                console.error(error);
                document.getElementById('feed-data').innerHTML = `<p>エラーが発生しました。</p>`;
            }
        });
    }

    // ★★★ ページ読み込み時にフィードデータを取得して表示 ★★★
    async function loadFeedData() {
        let region = getCookie('selected_region');
        let prefecture = getCookie('selected_prefecture');
        const feedType = getCookie('selected_feed_type') || 'extra'; // デフォルト値

        // URLパラメータをチェックし、クッキーよりも優先する
        const urlParams = new URLSearchParams(window.location.search);
        const urlRegion = urlParams.get('region');
        const urlPrefecture = urlParams.get('prefecture');

        if (urlRegion) {
          region = urlRegion;
        }
        if (urlPrefecture) {
          prefecture = urlPrefecture
        }

        if (region && prefecture) {
            const encodedRegion = encodeURIComponent(region);
            const encodedPrefecture = encodeURIComponent(prefecture);
            const rssUrl = `/rss/${feedType}?region=${encodedRegion}&prefecture=${encodedPrefecture}`;
            console.log(rssUrl)
            try {
                const response = await fetch(rssUrl, { credentials: 'same-origin' });
                if (response.ok) {
                    const htmlContent = await response.text();
                    document.getElementById('feed-data').innerHTML = htmlContent;
                } else {
                    document.getElementById('feed-data').innerHTML = `<p>フィードの取得に失敗しました。</p>`;
                }
            } catch (error) {
                console.error(error);
                document.getElementById('feed-data').innerHTML = `<p>エラーが発生しました。</p>`;
            }
        }
    }

    loadFeedData(); // ページロード時に実行

    // region が変更されたら、prefectureSelectを更新
    if (regionSelect) {
        regionSelect.addEventListener('change', updatePrefectures);
    }
});
