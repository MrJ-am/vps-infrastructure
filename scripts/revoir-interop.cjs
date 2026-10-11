'use strict';
// Parseur Babel déjà embarqué dans Playwright de Matheval : aucun paquet ajouté.
// Parsing seulement ; pas d'exécution du JS inspecté, config/plugins externes fermés.
const fs = require('node:fs');
const { babelParse, traverse } = require(process.argv[2]);
const sources = JSON.parse(fs.readFileSync(0, 'utf8'));
const errors = [];
function property(node) {
  if (!node) return null;
  if (node.computed) return node.property?.type === 'StringLiteral' ? node.property.value : null;
  return node.property?.name;
}
for (const source of sources) {
  try {
    const ast = babelParse(source.content, 'controle.js', true);
    function reject(path, capability) {
      const fn = path.getFunctionParent();
      const name = fn?.node.id?.name || (fn?.parentPath.node.type === 'VariableDeclarator' ? fn.parentPath.node.id.name : null);
      // Seule la création de balises techniques littérales et détachées est
      // déléguée. Le même adaptateur ne gagne aucun droit style/HTML/animation.
      const node = path.node;
      const call = path.parentPath?.node;
      const tag = call?.arguments?.[0];
      const allowed = capability === 'presentation-dom'
        && property(node) === 'createElement'
        && node.object?.type === 'Identifier' && node.object.name === 'document'
        && call?.type === 'CallExpression' && call.callee === node
        && tag?.type === 'StringLiteral'
        && source.exceptions.some(e => e.fonction === name
          && e.capacite === capability && e.operation === 'createElement'
          && e.balises?.includes(tag.value));
      if (!allowed) {
        errors.push({ fichier: source.path, ligne: path.node.loc?.start.line, capacite: capability, fonction: name });
      }
    }
    traverse(ast, {
      'MemberExpression|OptionalMemberExpression'(path) {
        const name = property(path.node);
        if (['style', 'classList', 'className', 'innerHTML', 'outerHTML', 'createElement', 'createElementNS', 'insertAdjacentHTML'].includes(name)) reject(path, 'presentation-dom');
      },
      'CallExpression|OptionalCallExpression'(path) {
        const callee = path.node.callee;
        const name = callee.type === 'Identifier' ? callee.name : property(callee);
        if (['animate', 'requestAnimationFrame', 'setInterval'].includes(name)) reject(path, 'animation');
        if (['insertAdjacentHTML', 'insertRule', 'replaceSync'].includes(name)) reject(path, 'presentation-dom');
        if (name === 'setAttribute') {
          const attr = path.node.arguments[0];
          if (attr?.type !== 'StringLiteral' || ['style', 'class'].includes(attr.value)) reject(path, 'presentation-dom');
        }
      },
      NewExpression(path) {
        if (path.node.callee.name === 'CSSStyleSheet') reject(path, 'presentation-dom');
      },
      ImportDeclaration(path) {
        if (/\.(?:css|scss|less)$/.test(path.node.source.value)) reject(path, 'presentation-css');
      }
    });
  } catch (e) {
    errors.push({ fichier: source.path, erreur: 'Parsing refusé : ' + e.message.slice(0, 300) });
  }
}
process.stdout.write(JSON.stringify(errors));
if (errors.length) process.exitCode = 1;
