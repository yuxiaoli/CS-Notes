(() => {
  const search = document.querySelector("#search");
  if (!search) return;
  search.closest(".search").hidden = false;
  const topics = [...document.querySelectorAll("[data-topic]")];
  const status = document.querySelector("#search-status");
  const normalize = value => value.normalize("NFKC").toLocaleLowerCase().trim();
  function filter() {
    const query = normalize(search.value), words = query.split(/\s+/).filter(Boolean);
    let matches = 0;
    for (const topic of topics) {
      let visible = 0;
      const label = normalize(topic.querySelector("h2").textContent);
      for (const item of topic.querySelectorAll("[data-title]")) {
        const needle = label + " " + item.dataset.title;
        const match = words.every(word => needle.includes(word));
        item.hidden = !match;
        if (match) visible++;
      }
      topic.hidden = visible === 0;
      matches += visible;
    }
    status.textContent = query ? (matches ? `找到 ${matches} 篇笔记` : "没有匹配的笔记") : "";
  }
  search.addEventListener("input", filter);
  search.addEventListener("keydown", event => {
    if (event.key === "Escape") { search.value = ""; filter(); }
    if (event.key === "Enter") {
      const first = document.querySelector("[data-topic]:not([hidden]) li:not([hidden]) a");
      if (first) { event.preventDefault(); first.focus(); }
    }
  });
})();
