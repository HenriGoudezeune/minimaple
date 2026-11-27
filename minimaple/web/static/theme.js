(function(){try{if(matchMedia("(max-width:700px)").matches)document.documentElement.classList.add("m")}catch(e){}
var d=document.documentElement,T=["light","dark","hygra","maple"];
function set(t){if(T.indexOf(t)<0)t="";if(t)d.dataset.theme=t;else d.removeAttribute("data-theme");try{localStorage.setItem("theme",t)}catch(e){}
document.querySelectorAll(".themebtns button").forEach(function(b){b.setAttribute("aria-pressed",String(b.dataset.t===t||(!t&&b.dataset.t===(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"))))})}
var cur="";try{cur=localStorage.getItem("theme")||"";if(cur==="apple")cur=""}catch(e){}set(cur);
document.addEventListener("DOMContentLoaded",function(){set(d.dataset.theme||"");document.querySelectorAll(".themebtns button").forEach(function(b){b.onclick=function(){set(b.dataset.t)}})})})();
