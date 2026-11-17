'use strict';
(() => {
  const toggle=document.getElementById('menu-toggle');
  const menu=document.getElementById('mobile-nav');
  if(toggle && menu){
    const setOpen = open => {
      menu.hidden = !open;
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
    };
    toggle.addEventListener('click', () => setOpen(menu.hidden));
    document.addEventListener('keydown', event => { if(event.key==='Escape')setOpen(false); });
    menu.addEventListener('click', event => {if(event.target.closest('a'))setOpen(false);});
    document.addEventListener('click', event => {
      if(!menu.hidden && !menu.contains(event.target) && !toggle.contains(event.target))setOpen(false);
    });
  }
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if(!window.confirm(form.getAttribute('data-confirm') || 'Подтвердить действие?'))event.preventDefault();
    });
  });
})();
