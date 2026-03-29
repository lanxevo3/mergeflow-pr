p=r'C:\Users\lanxe\Singularity\external\openclaw_fresh\workspace\pr-merge-saas\templates\dashboard.html'
o=open(p,'a',encoding='utf-8')
o.write('<h2>Your Repositories</h2>')
o.write('{%if repos%}<table class="t"><thead><tr><th>Repository</th><th>Branch</th><th>Status</th><th></th></tr></thead><tbody>')
o.write('{%for r in repos%}<tr><td>{{r.name}}</td><td>{{r.branch}}</td><td><span class="{%if r.enabled%}on{%else%}off{%endif%}">{%if r.enabled%}ON{%else%}OFF{%endif%}</span></td><td><button class="del" onclick="delRepo({{r.id}})">Remove</button></td></tr>{%endfor%}</tbody></table>{%else%}<div class="empty"><h3>No repos added yet</h3><p>Add your first repo below to start auto-merging PRs</p></div>{%endif%}')