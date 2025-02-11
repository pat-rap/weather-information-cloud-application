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
    console.log("DOMContentLoaded event fired");

    const regionSelect = document.getElementById('region');
    const feedTypeSelect = document.getElementById('feed_type');
    const fontIncreaseBtn = document.getElementById('font-increase');
    const fontDecreaseBtn = document.getElementById('font-decrease');
    const themeToggleBtn = document.getElementById('theme-toggle');

    // クッキーから selected_region を取得し、region セレクトボックスの値を設定
    if (regionSelect) {
        const selectedRegion = getCookie('selected_region');
        if (selectedRegion) {
            regionSelect.value = decodeURIComponent(selectedRegion);
            updatePrefectures(); // region がある場合のみ実行
        }
    }

    // selected_feed_type をクッキーから取得し、該当する項目を選択状態にする
    if (feedTypeSelect) {
        const selectedFeedType = getCookie('selected_feed_type');
        if (selectedFeedType) {
            feedTypeSelect.value = selectedFeedType;
        } else {
            feedTypeSelect.value = "extra";
            setCookie('selected_feed_type', 'extra');
        }
    }

    // 文字サイズ変更
    let currentFontSize = parseFloat(window.getComputedStyle(document.body).fontSize) || 16;

    if (fontIncreaseBtn) {
        fontIncreaseBtn.addEventListener('click', () => {
            console.log("Font increase button clicked");
            currentFontSize = Math.min(currentFontSize + 2, 36);
            document.body.style.fontSize = currentFontSize + 'px';
        });
    }

    if (fontDecreaseBtn) {
        fontDecreaseBtn.addEventListener('click', () => {
            console.log("Font decrease button clicked");
            currentFontSize = Math.max(currentFontSize - 2, 10);
            document.body.style.fontSize = currentFontSize + 'px';
        });
    }

    // テーマ切替
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            console.log("Theme toggle button clicked");
            document.body.classList.toggle('dark-mode');
        });
    }

    // フォーム送信時のイベントハンドラー
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const formData = new FormData(form);
            const region = formData.get('region');
            const prefecture = formData.get('prefecture');
            const feedType = formData.get('feed_type');

            setCookie('selected_region', region);
            setCookie('selected_prefecture', prefecture);
            setCookie('selected_feed_type', feedType);

            const encodedRegion = encodeURIComponent(region);
            const encodedPrefecture = encodeURIComponent(prefecture);
            const rssUrl = `/rss/${feedType}?region=${encodedRegion}&prefecture=${encodedPrefecture}`;

            try {
                const response = await fetch(rssUrl, { credentials: 'same-origin' });
                if (response.ok) {
                    document.getElementById('feed-data').innerHTML = await response.text();
                } else {
                    document.getElementById('feed-data').innerHTML = `<p>フィードの取得に失敗しました。</p>`;
                }
            } catch (error) {
                console.error(error);
                document.getElementById('feed-data').innerHTML = `<p>エラーが発生しました。</p>`;
            }
        });
    }

    // ページ読み込み時にフィードデータを取得して表示
    if (regionSelect) {
        async function loadFeedData() {
            let region = getCookie('selected_region');
            let prefecture = getCookie('selected_prefecture');
            const feedType = getCookie('selected_feed_type') || 'extra';
    
            const urlParams = new URLSearchParams(window.location.search);
            const urlRegion = urlParams.get('region');
            const urlPrefecture = urlParams.get('prefecture');
    
            if (urlRegion) region = urlRegion;
            if (urlPrefecture) prefecture = urlPrefecture;
    
            if (region && prefecture) {
                const encodedRegion = encodeURIComponent(region);
                const encodedPrefecture = encodeURIComponent(prefecture);
                const rssUrl = `/rss/${feedType}?region=${encodedRegion}&prefecture=${encodedPrefecture}`;
                console.log(rssUrl)
                try {
                    const response = await fetch(rssUrl, { credentials: 'same-origin' });
                    if (response.ok) {
                        document.getElementById('feed-data').innerHTML = await response.text();
                    } else {
                        document.getElementById('feed-data').innerHTML = `<p>フィードの取得に失敗しました。</p>`;
                    }
                } catch (error) {
                    console.error(error);
                    document.getElementById('feed-data').innerHTML = `<p>エラーが発生しました。</p>`;
                }
            }
        }
        loadFeedData();
        regionSelect.addEventListener('change', updatePrefectures);
    }
});
