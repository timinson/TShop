document.addEventListener('click', (event) => {
  if (event.defaultPrevented || event.button !== 0 || event.target.closest('a, button, input, select, textarea, label, [role="button"]')) return;
  if (window.getSelection().toString()) return;
  const row = event.target.closest('#result_list tbody tr');
  const link = row?.querySelector('th.field-id a');
  if (link) window.location.assign(link.href);
});
