"""Execute real Bash cleanup with fake Podman/sudo; no privileges or backups."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[1]/'scripts/p1-r1-acer-guarded-recovery-v2.sh'

class GuardTests(unittest.TestCase):
    def exercise(self, mode):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            scratch=root/'v79-r1-test'; scratch.mkdir()
            (scratch/'private').write_text('synthetic')
            work=root/'work'; work.mkdir()
            source=SRC.read_text().split('[[ "$(hostname)"')[0]
            source=source.replace('/dev/shm/v79-r1-*',str(root/'v79-r1-*'))
            program=source+f'''
WORK='{work}'
SWAP_ATTEMPTED=1
swap_names() {{ [[ -f '{root}/swap' ]] && echo /swapfile; return 0; }}
podman() {{
  [[ "$*" != *" -a "* ]] || return 125
  if [[ "$*" == *"pod ps"* ]]; then
    [[ '{mode}' != query_error ]] || return 125
    [[ '{mode}' == clear || -f '{root}/removed' ]] || echo r1-closed-0123456789
    return 0
  fi
  if [[ "$*" == *"pod rm"* ]]; then
    [[ '{mode}' != remove_error ]] || return 125
    touch '{root}/removed'; return 0
  fi
  return 125
}}
sudo() {{ [[ "$*" == 'swapon /swapfile' ]] || return 1; touch '{root}/swap'; }}
exit 0
'''
            r=subprocess.run(['bash','-c',program],capture_output=True,text=True)
            return r, scratch.exists(), (root/'swap').exists()

    def test_all_three_queries_use_supported_all_state_listing(self):
        s=SRC.read_text()
        self.assertNotIn('pod ps -a',s)
        self.assertGreaterEqual(s.count("pod ps --format '{{.Name}}'"),3)

    def test_clean_restores_swap(self):
        r,scratch,swap=self.exercise('clear')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertFalse(scratch); self.assertTrue(swap)

    def test_stopped_pod_removed_before_scratch_and_swap(self):
        r,scratch,swap=self.exercise('stopped')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertFalse(scratch); self.assertTrue(swap)

    def test_query_error_retains_ram_and_swap_disabled(self):
        r,scratch,swap=self.exercise('query_error')
        self.assertNotEqual(r.returncode,0)
        self.assertTrue(scratch); self.assertFalse(swap)

    def test_remove_error_retains_ram_and_swap_disabled(self):
        r,scratch,swap=self.exercise('remove_error')
        self.assertNotEqual(r.returncode,0)
        self.assertTrue(scratch); self.assertFalse(swap)

if __name__=='__main__': unittest.main()
