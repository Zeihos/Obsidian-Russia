'use strict';
(()=>{
 const drawer=document.querySelector('#mobileDrawer');
 const toggle=document.querySelector('[data-menu-toggle]');
 if(toggle && drawer){
   toggle.addEventListener('click',()=>{
     const show=!drawer.classList.contains('open');
     drawer.classList.toggle('open',show);
     toggle.setAttribute('aria-expanded',String(show));
     drawer.setAttribute('aria-hidden',String(!show));
   });
 }
 const modal=document.querySelector('#searchModal');
 const input=document.querySelector('#globalSearch');
 const suggestions=document.querySelector('#searchSuggestions');
 let requestSeq=0;
 function openModal(){if(!modal)return;modal.classList.add('open');modal.setAttribute('aria-hidden','false');document.body.style.overflow='hidden';setTimeout(()=>input?.focus(),0)}
 function closeModal(){if(!modal)return;modal.classList.remove('open');modal.setAttribute('aria-hidden','true');document.body.style.overflow='';requestSeq++}
 document.querySelectorAll('[data-search-open]').forEach(el=>el.addEventListener('click',openModal));
 document.querySelectorAll('[data-search-close]').forEach(el=>el.addEventListener('click',closeModal));
 document.addEventListener('keydown',e=>{
   if((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='k'){e.preventDefault();openModal()}
   if(e.key==='Escape'){closeModal();if(drawer?.classList.contains('open'))toggle?.click()}
 });
 function element(type,cls,text){const el=document.createElement(type);if(cls)el.className=cls;if(text)el.textContent=text;return el}
 if(input&&suggestions){
   let delay=0;
   input.addEventListener('input',()=>{
     const q=input.value.trim();const seq=++requestSeq;
     clearTimeout(delay);
     suggestions.replaceChildren(element('div','search-empty',q.length<2?'Введите минимум 2 символа для быстрого поиска':'Поиск...'));
     if(q.length<2)return;
     delay=setTimeout(async()=>{
       try{
         const res=await fetch('/api/search?q='+encodeURIComponent(q),{headers:{'Accept':'application/json'}});
         if(!res.ok)throw Error('response');
         const data=await res.json();if(seq!==requestSeq)return;
         suggestions.replaceChildren();
         if(!data.length){suggestions.append(element('div','search-empty','Ничего не найдено. Нажмите Enter для полного поиска.'));return}
         for(const item of data){
           const a=element('a','suggestion');a.href='/article/'+encodeURIComponent(item.slug);
           a.append(element('span','suggestion-icon',item.icon));
           const description=element('span','');description.append(element('b','',item.title));description.append(element('small','',item.category));a.append(description);suggestions.append(a)
         }
       }catch{if(seq===requestSeq)suggestions.replaceChildren(element('div','search-empty','Поиск временно недоступен. Нажмите Enter.'))}
     },180)
   })
 }
 document.querySelectorAll('[data-copy-url]').forEach(b=>b.addEventListener('click',async()=>{
   try{await navigator.clipboard.writeText(location.href);b.textContent='Ссылка скопирована ✓'}catch{b.textContent='Скопируйте адрес из браузера'}
 }));
 document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{
   try{await navigator.clipboard.writeText(b.getAttribute('data-copy')||'');b.textContent='Скопировано ✓'}catch{b.textContent='Выделите путь вручную'}
 }));
 document.querySelectorAll('[data-confirm]').forEach(f=>f.addEventListener('submit',e=>{
   if(!window.confirm(f.getAttribute('data-confirm')||'Подтвердите действие'))e.preventDefault()
 }));
})();
