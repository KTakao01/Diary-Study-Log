(() => {
  const input = document.getElementById('article-search');
  const status = document.getElementById('search-status');
  if (!input || !status) return;

  const normalize = (text) => text.normalize('NFKC').toLocaleLowerCase('ja');
  const articles = [...document.querySelectorAll('[data-article]')];
  const groups = [...document.querySelectorAll('.article-group')];

  const filter = () => {
    const terms = normalize(input.value).trim().split(/\s+/).filter(Boolean);
    let visible = 0;
    for (const article of articles) {
      const text = normalize(article.dataset.search);
      article.hidden = !terms.every((term) => text.includes(term));
      if (!article.hidden) visible += 1;
    }
    for (const group of groups) {
      const count = group.querySelectorAll('[data-article]:not([hidden])').length;
      group.hidden = count === 0;
      group.querySelector('.article-count').textContent = `${count}件`;
    }
    status.textContent = visible === 0
      ? '該当する記事はありません。キーワードを変えてみてください。'
      : `${articles.length}件中 ${visible}件を表示`;
  };

  input.addEventListener('input', filter);
  filter();
})();
