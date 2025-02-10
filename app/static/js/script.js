async function updatePrefectures() {
    const regionSelect = document.getElementById('region');
    const prefectureSelect = document.getElementById('prefecture');
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
}

// クッキーから値を取得する関数
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

// ページ読み込み時に都道府県セレクトボックスを初期化
document.addEventListener('DOMContentLoaded', () => {
  updatePrefectures();

    // selected_feed_typeをクッキーから取得し、selectedにする
    const feedTypeSelect = document.getElementById('feed_type');
    const selectedFeedType = getCookie('selected_feed_type');
    if (selectedFeedType) {
        feedTypeSelect.value = selectedFeedType;
    }
});
