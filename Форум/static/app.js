'use strict';
const menu=document.getElementById('menu-toggle');
const nav=document.getElementById('mobile-nav');
if(menu && nav){
  menu.addEventListener('click',()=>{
    const opening=nav.hasAttribute('hidden');
    if(opening)nav.removeAttribute('hidden');else nav.setAttribute('hidden','');
    menu.setAttribute('aria-expanded',String(opening));
  });
}
for(const form of document.querySelectorAll('form[data-confirm]')){
  form.addEventListener('submit',event=>{
    if(!window.confirm(form.getAttribute('data-confirm')))event.preventDefault();
  });
}
