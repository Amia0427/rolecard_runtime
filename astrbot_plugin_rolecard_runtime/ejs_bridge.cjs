const ejs = require('ejs');

async function render(request) {
  const { context, worldbook, templates } = request;
  const getvar = (path, options = {}) => {
    const parts = path.split('.');
    if (parts[0] === 'stat_data' || parts[0] === 'state') parts.shift();
    const value = parts.reduce((value, key) => value?.[key], context.state);
    return value === undefined ? options.defaults : value;
  };
  const renderTemplate = (text) => ejs.render(text, {
    ...context,
    stat_data: context.state,
    getvar,
    getwi: async (name) => {
      if (!Object.hasOwn(worldbook, name)) throw new Error(`未找到世界书：${name}`);
      return renderTemplate(worldbook[name]);
    },
  }, { async: true });
  return Promise.all(templates.map(renderTemplate));
}

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', async () => {
  try {
    process.stdout.write(JSON.stringify(await render(JSON.parse(input))));
  } catch (error) {
    process.stderr.write(error.message);
    process.exitCode = 1;
  }
});
