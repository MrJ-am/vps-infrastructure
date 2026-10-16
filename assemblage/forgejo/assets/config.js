(() => {
  const nodes = [...document.querySelectorAll('.markup .math')];
  if (!nodes.length) return;
  const root = '/assets/forgejo-org';
  window.MathJax = {
    loader: {load: ['ui/safe'], paths: {mathjax: `${root}/mathjax`, fonts: `${root}/fonts`}},
    tex: {
      packages: ['base', 'ams', 'newcommand', 'noundefined'],
      inlineMath: [['\\(', '\\)']], displayMath: [['\\[', '\\]']],
      tags: 'ams', processEnvironments: true, processRefs: true,
      maxBuffer: 32768, maxMacros: 1000
    },
    output: {font: 'mathjax-newcm', fontPath: `${root}/font`,
      displayOverflow: 'linebreak', linebreaks: {inline: true, width: '100%', lineleading: 0.2}},
    chtml: {fontURL: `${root}/font/chtml/woff2`, dynamicPrefix: `${root}/font/chtml/dynamic`},
    options: {enableMenu: false,
      safeOptions: {allow: {URLs: 'safe', classes: 'none', cssIDs: 'none', styles: 'none'}}},
    startup: {typeset: false, pageReady: () => MathJax.typesetPromise(nodes).then(() => {
      document.documentElement.dataset.orgMathjax = 'ready';
    })}
  };
  const script = document.createElement('script');
  script.src = `${root}/mathjax/tex-chtml.js`;
  script.async = true;
  script.onerror = () => console.error('Unable to load local MathJax');
  document.head.appendChild(script);
})();
