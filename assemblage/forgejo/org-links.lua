-- Forgejo supplies the directory of the rendered document, including the
-- repository and branch/commit. Browser URL resolution alone is wrong when a
-- README is embedded in a repository/directory page. Change rendered links only:
-- the original [[file:relative.org]] remains usable in Emacs.
local prefix = os.getenv('GITEA_PREFIX_SRC')

function Link(link)
  local target = link.target
  if prefix and prefix ~= '' and target ~= ''
      and not target:match('^[%a][%w+.-]*:')
      and not target:match('^[/#?]') then
    link.target = prefix:gsub('/+$', '') .. '/' .. target
    return link
  end
end
