const form = document.querySelector('.analytics-filters');
const period = document.getElementById('id_period');
const mode = form?.querySelector('.analytics-mode');
const preset = form?.querySelector('.analytics-filter-preset');
const custom = form?.querySelector('.analytics-filter-custom');

if (form && period && mode && preset && custom) {
  const radios = [...mode.querySelectorAll('input')];
  const customOption = period.querySelector('option[value="custom"]');
  let lastPreset = period.value !== 'custom' ? period.value : '30';
  const renderMode = (isCustom) => {
    preset.hidden = isCustom;
    custom.hidden = !isCustom;
    radios.forEach((radio) => { radio.checked = radio.value === (isCustom ? 'custom' : 'preset'); });
    period.value = isCustom ? 'custom' : lastPreset;
  };
  mode.hidden = false;
  if (customOption) customOption.hidden = true;
  form.classList.add('analytics-filters-enhanced');
  renderMode(period.value === 'custom');
  radios.forEach((radio) => radio.addEventListener('change', () => renderMode(radio.value === 'custom')));
  period.addEventListener('change', () => {
    if (period.value !== 'custom') lastPreset = period.value;
  });
}
