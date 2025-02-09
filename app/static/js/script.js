function updatePrefectures() {
    const regionSelect = document.getElementById("region");
    const prefectureSelect = document.getElementById("prefecture");
    const selectedRegion = regionSelect.value;

    // 選択された地域に基づいて都道府県の選択肢を更新
    prefectureSelect.innerHTML = '<option value="">-- 選択してください --</option>'; // 一旦クリア

    if (selectedRegion) {
        fetch(`/get_prefectures?region=${selectedRegion}`) // /get_prefectures エンドポイントにリクエスト
            .then(response => response.json())
            .then(prefectures => {
                prefectures.forEach(pref => {
                    const option = document.createElement("option");
                    option.value = pref;
                    option.textContent = pref;
                    prefectureSelect.appendChild(option);
                });
            });
    }
}
