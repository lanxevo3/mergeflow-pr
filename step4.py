p='C:\\Users\\lanxe\\Singularity\\external\\openclaw_fresh\\workspace\\pr-merge-saas\\templates\\dashboard.html'
o=open(p,'a',encoding='utf-8')
o.write('<div class="ab"><h3>Add Repository</h3><form class="fr" onsubmit="ar(event)"><div class="fi"><label>Owner / Repo</label><input name="full_name" placeholder="e.g. lanxevo3/mergeflow-pr" required></div><div class="fi"><label>Branch</label><input name="branch" value="main"></div><button type="submit" class="bs">Add Repo</button></form></div>')
o.write('<footer>MergeFlow -- Autonomous GitHub PR Management -- 2026</footer>')
o.write('<script>async function ar(e){e.preventDefault();const fd=new FormData(e.target);const r=await fetch("/api/repos",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(Object.fromEntries(fd))});if(r.ok)location.reload();else alert(await r.text())}async function tr(id){await fetch("/api/repos/"+id+"/toggle",{method:"POST"});location.reload()}</script></body></html>')
o.close()
