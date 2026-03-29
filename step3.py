p='C:\\Users\\lanxe\\Singularity\\external\\openclaw_fresh\\workspace\\pr-merge-saas\\templates\\dashboard.html'
o=open(p,'a',encoding='utf-8')
o.write('</style></head><body>')
o.write('<header class="h"><h1 class="t">MergeFlow</h1><div class="r"><span class="b">{{ plan }}</span><a href="/logout" style="background:#da3633;color:white;padding:6px 14px;border-radius:6px;text-decoration:none;font-size:13px">Logout</a></div></header>')
o.write('{% if plan == "Free Trial" %}<div class="bn"><div><h3>Upgrade to unlock unlimited repos</h3><p>Individual plan from USD29/mo -- unlimited repos, dry-run mode, audit log</p></div><a href="/upgrade/individual" class="bg">Upgrade Now</a></div>{% endif %}')
o.write('<h2>Your Repositories</h2>{% if repos %}<table><thead><tr><th>Repository</th><th>Branch</th><th>Status</th><th>Actions</th></tr></thead><tbody>{% for r in repos %}<tr><td>{{ r.name }}</td><td>{{ r.branch }}</td><td><span class="s {{ \'e\' if r.enabled else \'d\' }}">{{ \'Enabled\' if r.enabled else \'Disabled\' }}</span></td><td><button class="btn btg" onclick="tr({{ r.id }})">Toggle</button></td></tr>{% endfor %}</tbody></table>{% else %}<div class="es"><h3>No repos configured</h3><p>Add your first repository below to start auto-merging PRs</p></div>{% endif %}')
o.close()
