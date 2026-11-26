(function(){try{if(matchMedia("(max-width:700px)").matches)document.documentElement.classList.add("m")}catch(e){}var d=document.documentElement;function set(t){if(t==="hygra")d.dataset.theme="hygra";else d.removeAttribute("data-theme");try{localStorage.setItem("theme",t)}catch(e){}
document.querySelectorAll(".themesw").forEach(function(b){b.setAttribute("aria-checked",String(t==="hygra"))})}
var cur="apple";try{cur=localStorage.getItem("theme")==="hygra"?"hygra":"apple"}catch(e){}set(cur);
document.addEventListener("DOMContentLoaded",function(){document.querySelectorAll(".themesw").forEach(function(b){b.setAttribute("aria-checked",String(d.dataset.theme==="hygra"));b.onclick=function(){set(d.dataset.theme==="hygra"?"apple":"hygra")}})})})();
