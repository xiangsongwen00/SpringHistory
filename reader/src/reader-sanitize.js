export function cleanReaderHtml(purifier, html) {
  return purifier.sanitize(html, {
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|hanji):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,
    FORBID_TAGS: ['iframe', 'form', 'input', 'script', 'style', 'object', 'embed'],
    FORBID_ATTR: ['srcdoc']
  })
}
