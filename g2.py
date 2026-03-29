p=r'C:\Users\lanxe\Singularity\external\openclaw_fresh\workspace\pr-merge-saas\templates\dashboard.html'
o=open(p,'a',encoding='utf-8')
o.write(':6px;font-size:13px;cursor:pointer;font-weight:600;height:34px}.sub:hover{background:#2ea043}.footer{text-align:center;color:#484f58;font-size:11px;padding-top:16px;border-top:1px solid #21262d;margin-top:40px}</style></head><body>')
o.write('<div class="top"><span class="logo">MergeFlow</span><div class="right"><span class="badge">{{plan}}</span><a href="/" class="btn logout">Logout</a></div></div>')
o.write('{%if plan=="Free Trial"%}<div class="banner"><div><h3>Upgrade to unlock unlimited repos</h3><p>$29/mo -- unlimited repos, dry-run mode, audit log</p></div><a href="/upgrade/individual" class="upbtn">Upgrade Now</a></div>{%endif%}')