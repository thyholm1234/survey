// Fælles sidekrom: skygge/kant på den klæbende topbar, når siden er scrollet (som på moderne SaaS-sider).
const bar = document.querySelector('.topbar, header.site');
const update = () => bar?.classList.toggle('scrolled', window.scrollY > 40);
window.addEventListener('scroll', update, { passive: true });
update();
