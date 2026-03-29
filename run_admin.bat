@echo off
echo test_admin_patch > "C:\Users\lanxe\Singularity\external\openclaw_fresh\workspace\pr-merge-saas\patch_status.txt"
python "C:\Users\lanxe\Singularity\external\openclaw_fresh\workspace\pr-merge-saas\admin_inject.py"
echo done >> "C:\Users\lanxe\Singularity\external\openclaw_fresh\workspace\pr-merge-saas\patch_status.txt"
