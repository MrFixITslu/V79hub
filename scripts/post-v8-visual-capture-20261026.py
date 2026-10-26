#!/usr/bin/env python3
"""Post-V8 encrypted V79 checkpoint for the exact 2026-10-26 live stack.\nCapture pauses only the three pinned apps and
the three observed timers. No recreate, deployment, provider calls or live restore.
Run on Acer. Recovery images, runtime inputs and private host state stay encrypted.
"""
import argparse
import base64
import datetime
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import types

POST_V8_CHECKPOINT_SOURCE_PIN='2026-10-26-v8-exact-runtime'
READINESS_B64='IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJSRUFELU9OTFkgY2hlY2twb2ludCByZWFkaW5lc3MgcGlubmVkIHRvIGhlYWx0aHkgVjggSHViL1RpcXVldCwgMjAyNi0xMC0yNi4KTmV2ZXIgcGF1c2VzLCBjYXB0dXJlcyBvciByZXN0b3JlcyBwcm9kdWN0aW9uLiBGb3JrIG9mIHRlc3RlZCAyMDI2LTEwLTI1IHNjcmlwdDsKb25seSB0d28gcGlubmVkIGFwcCBpbWFnZXMsIHNlYWxlZCBIdWIgY29uZmlnIGFuZCBpbmZvcm1hdGlvbmFsIHNvdXJjZSBjaGFuZ2VkLgoiIiIKaW1wb3J0IGFyZ3BhcnNlCmltcG9ydCBkYXRldGltZQppbXBvcnQgZmNudGwKaW1wb3J0IGhhc2hsaWIKaW1wb3J0IGpzb24KaW1wb3J0IG9zCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBvcnQgcmUKaW1wb3J0IHNodXRpbAppbXBvcnQgc29ja2V0CmltcG9ydCBzdGF0CmltcG9ydCBzdWJwcm9jZXNzCmltcG9ydCBzeXMKClJFQ0lQSUVOVCA9ICc0ODRDRjM5Q0UzN0EwMjg4NDQ5N0FEOUM0MUExNzEwMkQyODQyRUNFJwpBUFBTID0gKCd2NzktaHViJywgJ3Y3OS10aXF1ZXQtbWFuYWdlcicsICd2NzktYnVzaW5lc3MtYWdlbnQnKQpJTUFHRVMgPSB7CiAgICAndjc5LWh1Yic6ICdzaGEyNTY6NjZjYWEwOTlhZGYxMzIxYjcyYTkwYjIyZjgxMjU5ODFlNWE2ZDk5YjU5MjBjZWJhZTA0NTQ1NDFjY2NkOWZhNycsCiAgICAndjc5LXRpcXVldC1tYW5hZ2VyJzogJ3NoYTI1Njo4YTVlMTViMTU3MzJjZWQwM2U3N2Y0Y2VlYmIwMTlkOGVhMTEzODFiMTQ2NDU2NTM5MzNlOGU4MTQ0YTEzY2MwJywKICAgICd2NzktYnVzaW5lc3MtYWdlbnQnOiAnc2hhMjU2OjFiYTI2ZDIyMDU1YjUzZGM5OTI3ODY3M2I3NzRlNDgwMDA2MTQzZjgwMjIyNTA5YTMyNTVlNzVkNTQ1MjZmNGInLAogICAgJ3Y3OS1odWItcG9zdGdyZXMnOiAnc2hhMjU2OmIwZjk1NjBhMmRlMDgzZTJjYzczODJlNzVmODA4YzczODFhMzI4NTJhN2VjNDkxMTdkZWVkYjMwMGU1NTJiMjQnLAogICAgJ3RpcXVldC1wb3N0Z3Jlcyc6ICdzaGEyNTY6Y2Y3OGU3NjY4M2I5Y2E4YzU3MzNjYmJkY2U2YzkyNjJiNDViNjc2NzkzNGRkMGE5NWU2NzFmOWEwZmMyMDY4NScsCn0KSE9TVF9TVEFURSA9ICgKICAgICcuY29uZmlnL3Y3OS13b3JrZm9yY2UvZ29vZ2xlJywKICAgICcubG9jYWwvc2hhcmUvdjc5LXdvcmtmb3JjZS1vcGVyYXRpb25zJywKICAgICcubG9jYWwvc2hhcmUvdjc5LWFwcHJvdmVkLXRhc2std29ya2VyJywKKQpTVEFHRSA9ICdTVEFSVCcKCmRlZiBzdGFnZShuYW1lKToKICAgIGdsb2JhbCBTVEFHRQogICAgU1RBR0UgPSBuYW1lCgpjbGFzcyBIYWx0KEV4Y2VwdGlvbik6CiAgICBwYXNzCgpkZWYgbmVlZChvaywgY29kZSk6CiAgICBpZiBub3Qgb2s6CiAgICAgICAgcmFpc2UgSGFsdChjb2RlKQoKZGVmIGNhbGwoYXJncywgZGF0YT1Ob25lLCB0aW1lb3V0PTQ1KToKICAgIHRyeToKICAgICAgICBwID0gc3VicHJvY2Vzcy5ydW4oYXJncywgaW5wdXQ9ZGF0YSwgc3Rkb3V0PXN1YnByb2Nlc3MuUElQRSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgc3RkZXJyPXN1YnByb2Nlc3MuREVWTlVMTCwgdGltZW91dD10aW1lb3V0KQogICAgZXhjZXB0IChPU0Vycm9yLCBzdWJwcm9jZXNzLlRpbWVvdXRFeHBpcmVkKToKICAgICAgICByYWlzZSBIYWx0KCdSRUFEX0NPTU1BTkRfVU5BVkFJTEFCTEUnKSBmcm9tIE5vbmUKICAgIG5lZWQocC5yZXR1cm5jb2RlID09IDAsICdSRUFEX0NPTU1BTkRfRkFJTEVEX05PX1NFQ1JFVF9PVVRQVVQnKQogICAgcmV0dXJuIHAuc3Rkb3V0CgpkZWYgamNhbGwoYXJncyk6CiAgICByZXR1cm4ganNvbi5sb2FkcyhjYWxsKGFyZ3MpKQoKZGVmIHZhbHVlcyhvKToKICAgIHJldHVybiBkaWN0KHguc3BsaXQoJz0nLCAxKSBmb3IgeCBpbiBvWydDb25maWcnXS5nZXQoJ0VudicsIFtdKSBpZiAnPScgaW4geCkKCmRlZiBsb2NhbF9kb2NrZXIoaG9zdCk6CiAgICBuZWVkKG5vdCBvcy5lbnZpcm9uLmdldCgnRE9DS0VSX0hPU1QnKSBhbmQgbm90IG9zLmVudmlyb24uZ2V0KCdET0NLRVJfQ09OVEVYVCcpLCAnRE9DS0VSX09WRVJSSURFJykKICAgIGN0eCA9IGpjYWxsKFsnZG9ja2VyJywgJ2NvbnRleHQnLCAnaW5zcGVjdCddKQogICAgbmVlZChsZW4oY3R4KSA9PSAxIGFuZCBjdHhbMF1bJ0VuZHBvaW50cyddWydkb2NrZXInXVsnSG9zdCddIGluCiAgICAgICAgICgndW5peDovLy92YXIvcnVuL2RvY2tlci5zb2NrJywgJ3VuaXg6Ly8vcnVuL2RvY2tlci5zb2NrJyksICdET0NLRVJfTk9UX0xPQ0FMJykKICAgIG5lZWQoY2FsbChbJ2RvY2tlcicsICdpbmZvJywgJy0tZm9ybWF0JywgJ3t7Lk5hbWV9fSddKS5kZWNvZGUoKS5zdHJpcCgpID09IGhvc3QsICdET0NLRVJfREFFTU9OX0hPU1RfTUlTTUFUQ0gnKQoKZGVmIG1lbW9yeV9hdmFpbGFibGUoKToKICAgIGZvciBsaW5lIGluIFBhdGgoJy9wcm9jL21lbWluZm8nKS5yZWFkX3RleHQoKS5zcGxpdGxpbmVzKCk6CiAgICAgICAgaWYgbGluZS5zdGFydHN3aXRoKCdNZW1BdmFpbGFibGU6Jyk6CiAgICAgICAgICAgIHJldHVybiBpbnQobGluZS5zcGxpdCgpWzFdKSAqIDEwMjQKICAgIHJldHVybiAwCgpkZWYgb3ZlcmxhcChhLCBiKToKICAgIHJldHVybiBvcy5wYXRoLmNvbW1vbnBhdGgoW2EsIGJdKSBpbiAoYSwgYikKCmRlZiBwcml2YXRlX21ldGFkYXRhKHBhdGgpOgogICAgdHJ5OgogICAgICAgIHMgPSBwYXRoLmxzdGF0KCkKICAgICAgICByZXR1cm4geydwcmVzZW50JzogVHJ1ZSwgJ3JlZ3VsYXInOiBzdGF0LlNfSVNSRUcocy5zdF9tb2RlKSwKICAgICAgICAgICAgICAgICdkaXJlY3RvcnknOiBzdGF0LlNfSVNESVIocy5zdF9tb2RlKSwgJ293bmVkJzogcy5zdF91aWQgPT0gb3MuZ2V0dWlkKCksCiAgICAgICAgICAgICAgICAncHJpdmF0ZSc6IG5vdCAoc3RhdC5TX0lNT0RFKHMuc3RfbW9kZSkgJiAwbzA3Nyl9CiAgICBleGNlcHQgRmlsZU5vdEZvdW5kRXJyb3I6CiAgICAgICAgcmV0dXJuIHsncHJlc2VudCc6IEZhbHNlfQoKCkVYUEVDVEVEX0hVQl9TT1VSQ0VTPXsnL2hvbWUvZmlyZWxpb24vLnY3OS1oYXJkZW5lZC1wYWlyLXJlbGVhc2VzL3BhaXItMjAyNjEwMjZUMDAzNjA3Wi02ZTYwMDY3OTFmMzQvbWFuaWZlc3Qtdjc5LWh1Yi1jYW5kaWRhdGUuanNvbic6J2U3ODUyNzdhMzk3MDQ3NmMyMTRmYWRlOTI3NjNmYWM3YTQxYTkxNTFlY2U3MzY1YzY3YzhjYjJiNDM5MDIzYzYnfQpFWFBFQ1RFRF9NT1VOVFM9ewogJ3Y3OS1odWInOnsnL2FwcC9kYXRhJzooJ2JpbmQnLFRydWUpLCcvcnVuL3Y3OS13b3JrZm9yY2UtcmVwb3J0cyc6KCdiaW5kJyxGYWxzZSksJy9ydW4vc2VjcmV0cy92NzktYWdlbnQtdG9rZW4nOignYmluZCcsRmFsc2UpLCcvcnVuL3NlY3JldHMvdjc5LWNvby1naXRodWItdG9rZW4nOignYmluZCcsRmFsc2UpLCcvcnVuL3NlY3JldHMvdjc5LXJlYWRvbmx5LXBsYXRmb3JtLXRva2VuJzooJ2JpbmQnLEZhbHNlKSwnL3J1bi9zZWNyZXRzL3Y3OS13b3JrZm9yY2UtdG9rZW4nOignYmluZCcsRmFsc2UpLCcvcnVuL3Y3OS1nb29nbGUnOigndm9sdW1lJyxGYWxzZSl9LAogJ3Y3OS10aXF1ZXQtbWFuYWdlcic6eycvYXBwL2RhdGEnOigndm9sdW1lJyxUcnVlKSwnL2FwcC91cGxvYWRzJzooJ3ZvbHVtZScsVHJ1ZSl9LAogJ3Y3OS1idXNpbmVzcy1hZ2VudCc6eycvcnVuL3NlY3JldHMvdjc5LWFnZW50LXRva2VuJzooJ2JpbmQnLEZhbHNlKX0sCn0KUFJJQ0lOR19QUk9CRT1yIiIiCmltcG9ydCBmcyBmcm9tICdub2RlOmZzJztpbXBvcnQgcGF0aCBmcm9tICdub2RlOnBhdGgnO2ltcG9ydCBjcnlwdG8gZnJvbSAnbm9kZTpjcnlwdG8nOwppbXBvcnQge2NyZWF0ZVByaWNpbmdSZXF1ZXN0U3RvcmV9IGZyb20gJy4vc2VydmVyL3ByaWNpbmctcmVxdWVzdC1zdG9yZS5tanMnOwppbXBvcnQge2dldFdpcGF5Q29uZmlnfSBmcm9tICcuL3NlcnZlci93aXBheS1wcm92aWRlci5tanMnOwp0cnl7CmNvbnN0IHJhdz1mcy5yZWFkRmlsZVN5bmMoJy9hcHAvc2VydmVyLnRzJyk7aWYoY3J5cHRvLmNyZWF0ZUhhc2goJ3NoYTEnKS51cGRhdGUoQnVmZmVyLmZyb20oJ2Jsb2IgJytyYXcubGVuZ3RoKydcMCcpKS51cGRhdGUocmF3KS5kaWdlc3QoJ2hleCcpIT09JzY3ODRkZWY5YTM4ZDAxOGY4N2FhODVlMGQ3M2VjMTBkNjU5NzJkYWYnKXByb2Nlc3MuZXhpdCgyKTsKY29uc3QgZmlsZT1wYXRoLnJlc29sdmUocHJvY2Vzcy5lbnYuREFUQV9ESVJ8fCcvYXBwL2RhdGEnLCdwcmljaW5nLXJlcXVlc3RzLXYxLmpzb24nKTtjb25zdCBzdD1mcy5sc3RhdFN5bmMoZmlsZSk7CmlmKCFzdC5pc0ZpbGUoKXx8KHN0Lm1vZGUmMG8wNzcpfHxmcy5leGlzdHNTeW5jKGZpbGUrJy5sb2NrJyl8fGdldFdpcGF5Q29uZmlnKCkuZW52aXJvbm1lbnQhPT0nc2FuZGJveCcpcHJvY2Vzcy5leGl0KDMpOwpjb25zdCBzZWNyZXQ9U3RyaW5nKHByb2Nlc3MuZW52LlY3OV9IVUJfU0VDVVJJVFlfS0VZfHxwcm9jZXNzLmVudi5WNzlfUExBVEZPUk1fU0hBUkVEX1NFQ1JFVHx8JycpLnRyaW0oKTsKY29uc3Qgc3RhdGU9YXdhaXQgY3JlYXRlUHJpY2luZ1JlcXVlc3RTdG9yZSh7ZmlsZSxzZWNyZXR9KS5yZWFkKCk7CmNvbnNvbGUubG9nKEpTT04uc3RyaW5naWZ5KHtwcmVzZW50OnRydWUscHJpdmF0ZTp0cnVlLHNpZ25hdHVyZVZlcmlmaWVkOnRydWUscmVxdWVzdHM6c3RhdGUucmVxdWVzdHMubGVuZ3RoLGV2ZW50czpzdGF0ZS5ldmVudHMubGVuZ3RoLHdpcGF5U2FuZGJveDp0cnVlLHNvdXJjZVBpbm5lZDp0cnVlfSkpOwp9Y2F0Y2h7cHJvY2Vzcy5leGl0KDQpfQoiIiIKZGVmIHZhbGlkYXRlX2ZpbmFsX3Njb3BlKHJlcG9ydCxzZWxlY3RlZCk6CiBmb3IgYXBwLGV4cGVjdGVkIGluIEVYUEVDVEVEX01PVU5UUy5pdGVtcygpOgogIHJvdz1zZWxlY3RlZFthcHBdO2FjdHVhbD17bVsnRGVzdGluYXRpb24nXToobVsnVHlwZSddLG1bJ1JXJ10pIGZvciBtIGluIHJvd1snTW91bnRzJ119CiAgbmVlZChhY3R1YWw9PWV4cGVjdGVkLCdGSU5BTF9BUFBMSUNBVElPTl9NT1VOVF9TQ09QRV9ESUZGRVJTJykKICBpZiBhcHA9PSd2NzktaHViJzoKICAgcGF0aHM9cm93WydDb25maWcnXVsnTGFiZWxzJ11bJ2NvbS5kb2NrZXIuY29tcG9zZS5wcm9qZWN0LmNvbmZpZ19maWxlcyddLnNwbGl0KCcsJykKICAgbmVlZChzZXQocGF0aHMpPT1zZXQoRVhQRUNURURfSFVCX1NPVVJDRVMpLCdGSU5BTF9IVUJfQ09NUE9TRV9DSEFJTl9ESUZGRVJTJykKICAgbmVlZChhbGwocmVwb3J0Wydjb21wb3NlX2lucHV0X2hhc2hlcyddLmdldChwKT09ZGlnZXN0IGZvciBwLGRpZ2VzdCBpbiBFWFBFQ1RFRF9IVUJfU09VUkNFUy5pdGVtcygpKSwnRklOQUxfSFVCX0NPTVBPU0VfSEFTSF9ESUZGRVJTJykKICAgZ29vZ2xlPW5leHQobSBmb3IgbSBpbiByb3dbJ01vdW50cyddIGlmIG1bJ0Rlc3RpbmF0aW9uJ109PScvcnVuL3Y3OS1nb29nbGUnKQogICBuZWVkKGdvb2dsZS5nZXQoJ05hbWUnKT09J3Y3OS1nb29nbGUtY3JlZGVudGlhbHMtNDlmODEzNzc2NzVhJywnR09PR0xFX0NSRURFTlRJQUxfVk9MVU1FX0RJRkZFUlMnKQogbWV0YWRhdGE9anNvbi5sb2FkcyhjYWxsKFsnZG9ja2VyJywnZXhlYycsJ3Y3OS1odWInLCdub2RlJywnLS1pbnB1dC10eXBlPW1vZHVsZScsJy1lJyxQUklDSU5HX1BST0JFXSkpCiBuZWVkKGFsbChtZXRhZGF0YS5nZXQoaykgaXMgVHJ1ZSBmb3IgayBpbiAoJ3ByZXNlbnQnLCdwcml2YXRlJywnc2lnbmF0dXJlVmVyaWZpZWQnLCd3aXBheVNhbmRib3gnLCdzb3VyY2VQaW5uZWQnKSksJ1BSSUNJTkdfTEVER0VSX09SX1NBTkRCT1hfQ0hFQ0tfRkFJTEVEJykKIG5lZWQoaXNpbnN0YW5jZShtZXRhZGF0YS5nZXQoJ3JlcXVlc3RzJyksaW50KSBhbmQgbWV0YWRhdGFbJ3JlcXVlc3RzJ10+PTEsJ0FDQ0VQVEVEX1BSSUNJTkdfUkVRVUVTVF9OT1RfRk9VTkQnKQogcmVwb3J0WydwcmljaW5nX2xlZGdlcl9tZXRhZGF0YSddPW1ldGFkYXRhCiByZXBvcnRbJ21vdW50X2NvdW50J109c3VtKGxlbih2KSBmb3IgdiBpbiBFWFBFQ1RFRF9NT1VOVFMudmFsdWVzKCkpCiByZXBvcnRbJ2V4cGVjdGVkX2VuY3J5cHRlZF9hcnRpZmFjdHMnXT01K3JlcG9ydFsnbW91bnRfY291bnQnXQogcmVwb3J0WydjdXJyZW50X2h1Yl9zb3VyY2UnXT0nYzEyZTU0YmRiNTJmODk5NmZhZTE5Njg4ZDc0MzU0ZDczMWU3ZGUyNycKIHJlcG9ydFsnbW91bnRlZF9nb29nbGVfY3JlZGVudGlhbHNfY29udGVudHNfcmVhZCddPUZhbHNlCiByZXBvcnRbJ2ZpbmFsX3JlY292ZXJ5X3Njb3BlJ109J0ZJVkVfQ1VSUkVOVF9JTUFHRVNfVFdPX0RBVEFCQVNFU19URU5fTU9VTlRTX1BSSVZBVEVfSE9TVF9TVEFURScKCmRlZiBzZXJ2ZXIoKToKICAgIHN0YWdlKCdTRVJWRVJfSURFTlRJVFlfQU5EX0RPQ0tFUicpCiAgICBuZWVkKHNvY2tldC5nZXRob3N0bmFtZSgpID09ICd2NzlzbCcgYW5kIG9zLmdldGV1aWQoKSAhPSAwIGFuZAogICAgICAgICBQYXRoLmhvbWUoKSA9PSBQYXRoKCcvaG9tZS9maXJlbGlvbicpLCAnV1JPTkdfU0VSVkVSX1VTRVInKQogICAgbG9jYWxfZG9ja2VyKCd2NzlzbCcpCiAgICBuYW1lcyA9IGNhbGwoWydkb2NrZXInLCAncHMnLCAnLS1hbGwnLCAnLS1mb3JtYXQnLCAne3suTmFtZXN9fSddKS5kZWNvZGUoKS5zcGxpdGxpbmVzKCkKICAgIHJvd3MgPSBqY2FsbChbJ2RvY2tlcicsICdpbnNwZWN0JywgKm5hbWVzXSkKICAgIGFsbF9yb3dzID0ge3JbJ05hbWUnXS5sc3RyaXAoJy8nKTogciBmb3IgciBpbiByb3dzfQogICAgbmVlZChzZXQoSU1BR0VTKSA8PSBzZXQoYWxsX3Jvd3MpLCAnUkVRVUlSRURfQ09OVEFJTkVSX0FCU0VOVCcpCiAgICBzZWxlY3RlZCA9IHtuOiBhbGxfcm93c1tuXSBmb3IgbiBpbiBJTUFHRVN9CiAgICBibG9ja2VycywgcGlucywgY29tcG9zZV9pbnB1dHMsIG1vdW50cyA9IFtdLCB7fSwge30sIFtdCiAgICBpbWFnZV9ieXRlcyA9IDAKICAgIGZvciBuYW1lLCBvIGluIHNlbGVjdGVkLml0ZW1zKCk6CiAgICAgICAgc3RhZ2UoJ1NFUlZFUl9DT05UQUlORVJfJyArIG5hbWUucmVwbGFjZSgnLScsICdfJykudXBwZXIoKSkKICAgICAgICBoZWFsdGh5ID0gb1snU3RhdGUnXS5nZXQoJ1J1bm5pbmcnKSBhbmQgb1snU3RhdGUnXS5nZXQoJ0hlYWx0aCcsIHt9KS5nZXQoJ1N0YXR1cycpID09ICdoZWFsdGh5JwogICAgICAgIG5lZWQob1snSW1hZ2UnXSA9PSBJTUFHRVNbbmFtZV0gYW5kIGhlYWx0aHksICdQSU5ORURfSU1BR0VfT1JfSEVBTFRIX0NIQU5HRUQnKQogICAgICAgIHBpbnNbbmFtZV0gPSB7J2lkJzogb1snSWQnXSwgJ2ltYWdlJzogb1snSW1hZ2UnXSwgJ2hlYWx0aHknOiBUcnVlfQogICAgICAgIGltYWdlX2J5dGVzICs9IGpjYWxsKFsnZG9ja2VyJywgJ2ltYWdlJywgJ2luc3BlY3QnLCBvWydJbWFnZSddXSlbMF1bJ1NpemUnXQogICAgICAgIGxhYmVscyA9IG9bJ0NvbmZpZyddLmdldCgnTGFiZWxzJykgb3Ige30KICAgICAgICBwYXRocyA9IGxhYmVscy5nZXQoJ2NvbS5kb2NrZXIuY29tcG9zZS5wcm9qZWN0LmNvbmZpZ19maWxlcycsICcnKS5zcGxpdCgnLCcpCiAgICAgICAgbmVlZChhbGwocC5zdGFydHN3aXRoKCcvJykgZm9yIHAgaW4gcGF0aHMpLCAnQ09NUE9TRV9DSEFJTl9VTkFWQUlMQUJMRScpCiAgICAgICAgZm9yIHRleHQgaW4gcGF0aHM6CiAgICAgICAgICAgIHAgPSBQYXRoKHRleHQpCiAgICAgICAgICAgIHMgPSBwLmxzdGF0KCkKICAgICAgICAgICAgbmVlZChzdGF0LlNfSVNSRUcocy5zdF9tb2RlKSBhbmQgcy5zdF9zaXplIDw9IDIqMTAyNCoqMiBhbmQKICAgICAgICAgICAgICAgICBzLnN0X3VpZCBpbiAoMCwgb3MuZ2V0dWlkKCkpIGFuZCBub3Qgcy5zdF9tb2RlICYgMG8wMDIsICdDT01QT1NFX0lOUFVUX1VOU0FGRScpCiAgICAgICAgICAgIGNvbXBvc2VfaW5wdXRzW3RleHRdID0gaGFzaGxpYi5zaGEyNTYocC5yZWFkX2J5dGVzKCkpLmhleGRpZ2VzdCgpCiAgICAgICAgaWYgbmFtZSBpbiBBUFBTOgogICAgICAgICAgICBmb3IgbSBpbiBvLmdldCgnTW91bnRzJywgW10pOgogICAgICAgICAgICAgICAgbmVlZChtWydUeXBlJ10gaW4gKCdiaW5kJywgJ3ZvbHVtZScpIGFuZCBtLmdldCgnU291cmNlJywgJycpLnN0YXJ0c3dpdGgoJy8nKSwgJ01PVU5UX1RZUEVfVU5SRVZJRVdFRCcpCiAgICAgICAgICAgICAgICBzb3VyY2UgPSBtWydTb3VyY2UnXQogICAgICAgICAgICAgICAgc2hhcmVkID0gW10KICAgICAgICAgICAgICAgIGZvciBvdGhlciwgZm9yZWlnbiBpbiBhbGxfcm93cy5pdGVtcygpOgogICAgICAgICAgICAgICAgICAgIGlmIG90aGVyIGluIEFQUFMgb3Igbm90IGZvcmVpZ25bJ1N0YXRlJ10uZ2V0KCdSdW5uaW5nJyk6CiAgICAgICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICAgICAgICAgZm9yIGZtIGluIGZvcmVpZ24uZ2V0KCdNb3VudHMnLCBbXSk6CiAgICAgICAgICAgICAgICAgICAgICAgIGlmIGZtLmdldCgnUlcnKSBhbmQgZm0uZ2V0KCdTb3VyY2UnKSBhbmQgb3ZlcmxhcChzb3VyY2UsIGZtWydTb3VyY2UnXSk6CiAgICAgICAgICAgICAgICAgICAgICAgICAgICBzaGFyZWQuYXBwZW5kKG90aGVyKQogICAgICAgICAgICAgICAgaWYgc2hhcmVkOgogICAgICAgICAgICAgICAgICAgIGJsb2NrZXJzLmFwcGVuZCgnU0hBUkVEX1dSSVRFUl8nICsgbmFtZSkKICAgICAgICAgICAgICAgIG1vdW50cy5hcHBlbmQoeydjb250YWluZXInOiBuYW1lLCAnZGVzdGluYXRpb24nOiBtWydEZXN0aW5hdGlvbiddLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgJ3R5cGUnOiBtWydUeXBlJ10sICdydyc6IG1bJ1JXJ10sICdvdGhlcl93cml0ZXJfY291bnQnOiBsZW4oc2V0KHNoYXJlZCkpfSkKICAgIGgsIHQgPSB2YWx1ZXMoc2VsZWN0ZWRbJ3Y3OS1odWInXSksIHZhbHVlcyhzZWxlY3RlZFsndjc5LXRpcXVldC1tYW5hZ2VyJ10pCiAgICBzdGFnZSgnU0VSVkVSX1NFQ1VSSVRZX0FORF9QUklDRV9JTlBVVFMnKQogICAgbmVlZChoLmdldCgnVjc5X1JFUVVJUkVfQURNSU5fTUZBJykgPT0gJzEnIGFuZAogICAgICAgICBoLmdldCgnVjc5X0hVQl9USVFVRVRfU0VTU0lPTl9CSU5ESU5HJykgPT0gJzEnIGFuZAogICAgICAgICB0LmdldCgnVjc5X1RJUVVFVF9TRVNTSU9OX0JJTkRJTkdfRU5BQkxFRCcpID09ICcxJyBhbmQKICAgICAgICAgdC5nZXQoJ1Y3OV9BTExPV19MRUdBQ1lfQVVUSCcpID09ICcwJyBhbmQKICAgICAgICAgdC5nZXQoJ1Y3OV9FTlRJVExFTUVOVF9SRUNIRUNLX0VOQUJMRUQnKSA9PSAnMScsICdTRUNVUklUWV9GTEFHU19DSEFOR0VEJykKICAgIG5lZWQoaC5nZXQoJ1Y3OV9USVFVRVRfTEFVTkNIX1NFQ1JFVCcpIGFuZAogICAgICAgICBoWydWNzlfVElRVUVUX0xBVU5DSF9TRUNSRVQnXSA9PSB0LmdldCgnVjc5X1RJUVVFVF9MQVVOQ0hfU0VDUkVUJyksICdTU09fU0VDUkVUX01JU01BVENIJykKICAgIHByaWNlX2lucHV0c19wcmVzZW50ID0gYWxsKHQuZ2V0KCdQTEFOX1BSSUNFXycgKyB4KSBmb3IgeCBpbiAoJ1NUQVJURVInLCdQUk8nLCdFTlRFUlBSSVNFJykpCiAgICBpZiBub3QgcHJpY2VfaW5wdXRzX3ByZXNlbnQ6CiAgICAgICAgYmxvY2tlcnMuYXBwZW5kKCdGUk9aRU5fUFJJQ0VfSU5QVVRfQUJTRU5UJykKICAgIGRiX3ZlcnNpb25zID0ge30KICAgIGZvciBkYiwgbWFqb3IgaW4gWygndjc5LWh1Yi1wb3N0Z3JlcycsICcxNycpLCAoJ3RpcXVldC1wb3N0Z3JlcycsICcxNicpXToKICAgICAgICBzdGFnZSgnU0VSVkVSX0RBVEFCQVNFXycgKyBtYWpvcikKICAgICAgICB2ZXJzaW9uID0gY2FsbChbJ2RvY2tlcicsJ2V4ZWMnLGRiLCdwZ19kdW1wJywnLS12ZXJzaW9uJ10pLmRlY29kZSgpCiAgICAgICAgbmVlZChyZS5zZWFyY2gocidQb3N0Z3JlU1FMXCkgJyttYWpvcityJ1wuJywgdmVyc2lvbiksICdQR19EVU1QX1ZFUlNJT05fQ0hBTkdFRCcpCiAgICAgICAgY2FsbChbJ2RvY2tlcicsJ2V4ZWMnLGRiLCdzaCcsJy1jJywKICAgICAgICAgICAgICAncGdfaXNyZWFkeSAtcSAtVSAiJHtQT1NUR1JFU19VU0VSOi1wb3N0Z3Jlc30iIC1kICIke1BPU1RHUkVTX0RCOi0ke1BPU1RHUkVTX1VTRVI6LXBvc3RncmVzfX0iJ10pCiAgICAgICAgZGJfdmVyc2lvbnNbZGJdID0geydtYWpvcic6IG1ham9yLCAncmVhZHknOiBUcnVlfQogICAgdGltZXJzID0gW10KICAgIHN0YWdlKCdTRVJWRVJfVElNRVJTX0FORF9IT1NUX1NUQVRFJykKICAgIGxpc3RpbmcgPSBjYWxsKFsnc3lzdGVtY3RsJywnLS11c2VyJywnbGlzdC11bml0cycsJy0tdHlwZT10aW1lcicsJy0tc3RhdGU9YWN0aXZlJywnLS1uby1sZWdlbmQnLCctLXBsYWluJ10pLmRlY29kZSgpCiAgICBmb3IgbGluZSBpbiBsaXN0aW5nLnNwbGl0bGluZXMoKToKICAgICAgICB1bml0ID0gbGluZS5zcGxpdCgpWzBdCiAgICAgICAgaWYgcmUuZnVsbG1hdGNoKHIndjc5Wy1BLVphLXowLTlAXy5dK1wudGltZXInLCB1bml0KSBhbmQgcmUuc2VhcmNoKHInd29ya2ZvcmNlfHJlbGVhc2V8dGFzaycsIHVuaXQpOgogICAgICAgICAgICB0aW1lcnMuYXBwZW5kKHVuaXQpCiAgICBob3N0X3N0YXRlID0ge3A6IHByaXZhdGVfbWV0YWRhdGEoUGF0aC5ob21lKCkvcCkgZm9yIHAgaW4gSE9TVF9TVEFURX0KICAgIGZvciBwLCBtZXRhIGluIGhvc3Rfc3RhdGUuaXRlbXMoKToKICAgICAgICBpZiBub3QgbWV0YS5nZXQoJ3ByZXNlbnQnKSBvciBub3QgbWV0YS5nZXQoJ2RpcmVjdG9yeScpIG9yIG5vdCBtZXRhLmdldCgnb3duZWQnKToKICAgICAgICAgICAgYmxvY2tlcnMuYXBwZW5kKCdIT1NUX1NUQVRFX1VOU0FGRV8nICsgcC5yc3BsaXQoJy8nLDEpWy0xXSkKICAgIGdvb2dsZSA9IHtuOiBwcml2YXRlX21ldGFkYXRhKFBhdGguaG9tZSgpL0hPU1RfU1RBVEVbMF0vbikgZm9yIG4gaW4gKCdjbGllbnQuanNvbicsJ2NyZWRlbnRpYWxzLmpzb24nKX0KICAgIGlmIG5vdCBhbGwobS5nZXQoJ3JlZ3VsYXInKSBhbmQgbS5nZXQoJ293bmVkJykgYW5kIG0uZ2V0KCdwcml2YXRlJykgZm9yIG0gaW4gZ29vZ2xlLnZhbHVlcygpKToKICAgICAgICBibG9ja2Vycy5hcHBlbmQoJ0dPT0dMRV9DUkVERU5USUFMX0ZJTEVfVU5TQUZFJykKICAgICMgSW5zcGVjdCBtZXRhZGF0YSBvbmx5OyBkbyBub3QgcmVhZCBjcmVkZW50aWFscyBvciBxdWV1ZSBwYXlsb2Fkcy4KICAgIHdvcmtmb3JjZV91bml0cyA9IFtdCiAgICB1bml0X3Jvb3QgPSBQYXRoLmhvbWUoKS8nLmNvbmZpZy9zeXN0ZW1kL3VzZXInCiAgICBpZiB1bml0X3Jvb3QuaXNfZGlyKCk6CiAgICAgICAgd29ya2ZvcmNlX3VuaXRzID0gc29ydGVkKHAubmFtZSBmb3IgcCBpbiB1bml0X3Jvb3QuaXRlcmRpcigpCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgaWYgcC5pc19maWxlKCkgYW5kIHJlLmZ1bGxtYXRjaChyJ3Y3OVstQS1aYS16MC05QF8uXStcLihzZXJ2aWNlfHRpbWVyKScscC5uYW1lKQogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGFuZCByZS5zZWFyY2gocid3b3JrZm9yY2V8cmVsZWFzZXx0YXNrJyxwLm5hbWUpKQogICAgbG9jayA9IFBhdGguaG9tZSgpLycudjc5LXBvcnRmb2xpby1yb2xsb3V0LmxvY2snCiAgICBpZiBsb2NrLmV4aXN0cygpOgogICAgICAgIG5lZWQobm90IGxvY2suaXNfc3ltbGluaygpIGFuZCBsb2NrLmlzX2ZpbGUoKSwgJ09QRVJBVElPTl9MT0NLX1VOU0FGRScpCiAgICAgICAgd2l0aCBsb2NrLm9wZW4oJ3JiJykgYXMgZjoKICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgZmNudGwuZmxvY2soZiwgZmNudGwuTE9DS19FWCB8IGZjbnRsLkxPQ0tfTkIpCiAgICAgICAgICAgICAgICBmY250bC5mbG9jayhmLCBmY250bC5MT0NLX1VOKQogICAgICAgICAgICBleGNlcHQgQmxvY2tpbmdJT0Vycm9yOgogICAgICAgICAgICAgICAgYmxvY2tlcnMuYXBwZW5kKCdPVEhFUl9SRUxFQVNFX09QRVJBVElPTl9SVU5OSU5HJykKICAgIGZvciBuIGluIHNlbGVjdGVkOgogICAgICAgIGN1cnJlbnQgPSBqY2FsbChbJ2RvY2tlcicsJ2luc3BlY3QnLG5dKVswXQogICAgICAgIG5lZWQoY3VycmVudFsnSWQnXSA9PSBzZWxlY3RlZFtuXVsnSWQnXSBhbmQgY3VycmVudFsnSW1hZ2UnXSA9PSBzZWxlY3RlZFtuXVsnSW1hZ2UnXSwgJ1JVTlRJTUVfQ0hBTkdFRF9EVVJJTkdfUFJFRkxJR0hUJykKICAgIHJlc3VsdCA9IHsnbW9kZSc6ICdSRUFEX09OTFlfQ0hFQ0tQT0lOVF9SRUFESU5FU1MnLCAnY2hlY2tlZF9hdCc6IGRhdGV0aW1lLmRhdGV0aW1lLm5vdyhkYXRldGltZS50aW1lem9uZS51dGMpLmlzb2Zvcm1hdCgpLAogICAgICAgICAgICAgICdwaW5zJzogcGlucywgJ2NvbXBvc2VfaW5wdXRfaGFzaGVzJzogY29tcG9zZV9pbnB1dHMsICdhcHBfbW91bnRzJzogbW91bnRzLAogICAgICAgICAgICAgICdpbWFnZV9ieXRlcyc6IGltYWdlX2J5dGVzLCAnc2VydmVyX2ZyZWVfYnl0ZXMnOiBzaHV0aWwuZGlza191c2FnZShQYXRoLmhvbWUoKSkuZnJlZSwKICAgICAgICAgICAgICAnc2VydmVyX2F2YWlsYWJsZV9tZW1vcnlfYnl0ZXMnOiBtZW1vcnlfYXZhaWxhYmxlKCksICdkYXRhYmFzZXMnOiBkYl92ZXJzaW9ucywKICAgICAgICAgICAgICAnYWN0aXZlX3RpbWVyc190b19xdWllc2NlJzogc29ydGVkKHRpbWVycyksICd3b3JrZm9yY2VfdW5pdF9maWxlcyc6IHdvcmtmb3JjZV91bml0cywKICAgICAgICAgICAgICAnaG9zdF9zdGF0ZV9tZXRhZGF0YSc6IGhvc3Rfc3RhdGUsICdnb29nbGVfZmlsZV9tZXRhZGF0YSc6IGdvb2dsZSwKICAgICAgICAgICAgICAnZnJvemVuX3ByaWNlX2lucHV0c19hdmFpbGFibGVfbm90X3ByaW50ZWQnOiBib29sKHByaWNlX2lucHV0c19wcmVzZW50KSwKICAgICAgICAgICAgICAnZ29vZ2xlX2NvbnRlbnRzX3JlYWQnOiBGYWxzZSwgJ3Byb2R1Y3Rpb25fY2hhbmdlZCc6IEZhbHNlLAogICAgICAgICAgICAgICdibG9ja2Vycyc6IHNvcnRlZChzZXQoYmxvY2tlcnMpKSwgJ2NhcHR1cmVfcGVyZm9ybWVkJzogRmFsc2UsICdyZXN0b3JlX3BlcmZvcm1lZCc6IEZhbHNlfQogICAgdmFsaWRhdGVfZmluYWxfc2NvcGUocmVzdWx0LHNlbGVjdGVkKQogICAgcmVzdWx0WydpbnZlbnRvcnlfc2hhMjU2J10gPSBoYXNobGliLnNoYTI1Nihqc29uLmR1bXBzKAogICAgICAgIHsncGlucyc6IHBpbnMsICdpbnB1dHMnOiBjb21wb3NlX2lucHV0cywgJ3RpbWVycyc6IHNvcnRlZCh0aW1lcnMpLCAnbW91bnRzJzogbW91bnRzLCAnZmluYWxfc2NvcGUnOnJlc3VsdFsnZmluYWxfcmVjb3Zlcnlfc2NvcGUnXX0sCiAgICAgICAgc29ydF9rZXlzPVRydWUpLmVuY29kZSgpKS5oZXhkaWdlc3QoKQogICAgcmV0dXJuIHJlc3VsdAoKZGVmIGFjZXIoKToKICAgIHN0YWdlKCdBQ0VSX0lERU5USVRZX0FORF9ET0NLRVInKQogICAgbmVlZChzb2NrZXQuZ2V0aG9zdG5hbWUoKSA9PSAnZmlyZWxpb24tQXNwaXJlLUEzMTUtNTEnIGFuZCBvcy5nZXRldWlkKCkgIT0gMCwgJ1JVTl9PTl9OT05ST09UX0FDRVInKQogICAgbG9jYWxfZG9ja2VyKHNvY2tldC5nZXRob3N0bmFtZSgpKQogICAgc3RhZ2UoJ0FDRVJfUkVDT1ZFUllfS0VZX01FVEFEQVRBJykKICAgIGZpbmdlcnByaW50cyA9IGNhbGwoWydncGcnLCctLWJhdGNoJywnLS13aXRoLWNvbG9ucycsJy0tZmluZ2VycHJpbnQnLFJFQ0lQSUVOVF0pLmRlY29kZSgpCiAgICBuZWVkKCdmcHI6Ojo6Ojo6OjonK1JFQ0lQSUVOVCsnOicgaW4gZmluZ2VycHJpbnRzLCAnUkVDT1ZFUllfUFVCTElDX0tFWV9VTkFWQUlMQUJMRScpCiAgICBrZXlzID0gY2FsbChbJ2dwZycsJy0tYmF0Y2gnLCctLXdpdGgtY29sb25zJywnLS1saXN0LXNlY3JldC1rZXlzJyxSRUNJUElFTlRdKS5kZWNvZGUoKQogICAgbmVlZChhbnkobGluZS5zdGFydHN3aXRoKCdzZWM6Jykgb3IgbGluZS5zdGFydHN3aXRoKCdzZWMjOicpIGZvciBsaW5lIGluIGtleXMuc3BsaXRsaW5lcygpKSwgJ1JFQ09WRVJZX1BSSVZBVEVfS0VZX1VOQVZBSUxBQkxFJykKICAgIHByaW50KCdBQ0VSX1JFQ09WRVJZX0tFWT1QSU5ORURfUFVCTElDX0FORF9QUklWQVRFX1BSRVNFTlQnLCBmbHVzaD1UcnVlKQogICAgcHJpbnQoJ0FDRVJfRlJFRV9CWVRFUz0nK3N0cihzaHV0aWwuZGlza191c2FnZShQYXRoLmhvbWUoKSkuZnJlZSksIGZsdXNoPVRydWUpCiAgICBwcmludCgnQUNFUl9BVkFJTEFCTEVfTUVNT1JZX0JZVEVTPScrc3RyKG1lbW9yeV9hdmFpbGFibGUoKSksIGZsdXNoPVRydWUpCiAgICBjb21tYW5kID0gWydzc2gnLCctVCcsJy1vJywnQmF0Y2hNb2RlPXllcycsJy1vJywnU3RyaWN0SG9zdEtleUNoZWNraW5nPXllcycsCiAgICAgICAgICAgICAgICctbycsJ0Nvbm5lY3RUaW1lb3V0PTEwJywnZmlyZWxpb25Adjc5c2wnLCdweXRob24zIC1CIC0gLS1zZXJ2ZXInXQogICAgc3RhZ2UoJ1NFUlZFUl9SRUFEX09OTFlfSU5WRU5UT1JZJykKICAgIHRyeToKICAgICAgICBwcm9jZXNzID0gc3VicHJvY2Vzcy5ydW4oY29tbWFuZCwgaW5wdXQ9UGF0aChfX2ZpbGVfXykucmVhZF9ieXRlcygpLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBzdGRvdXQ9c3VicHJvY2Vzcy5QSVBFLCBzdGRlcnI9c3VicHJvY2Vzcy5ERVZOVUxMLCB0aW1lb3V0PTE4MCkKICAgIGV4Y2VwdCAoT1NFcnJvciwgc3VicHJvY2Vzcy5UaW1lb3V0RXhwaXJlZCk6CiAgICAgICAgcmFpc2UgSGFsdCgnU1NIX1JFQURfVU5BVkFJTEFCTEUnKSBmcm9tIE5vbmUKICAgIHJhdyA9IHByb2Nlc3Muc3Rkb3V0CiAgICBpZiBwcm9jZXNzLnJldHVybmNvZGU6CiAgICAgICAgdHJ5OgogICAgICAgICAgICBlcnJvciA9IGpzb24ubG9hZHMocmF3KQogICAgICAgICAgICBmb3Iga2V5IGluICgnZXJyb3Jfc3RhZ2UnLCAnZXJyb3InKToKICAgICAgICAgICAgICAgIGlmIHJlLmZ1bGxtYXRjaChyJ1tBLVowLTlfXSsnLCBzdHIoZXJyb3IuZ2V0KGtleSwgJycpKSk6CiAgICAgICAgICAgICAgICAgICAgcHJpbnQoJ1NFUlZFUl8nICsga2V5LnVwcGVyKCkgKyAnPScgKyBlcnJvcltrZXldLCBmbHVzaD1UcnVlKQogICAgICAgIGV4Y2VwdCAoVmFsdWVFcnJvciwgVHlwZUVycm9yKToKICAgICAgICAgICAgcGFzcwogICAgICAgIHJhaXNlIEhhbHQoJ1NFUlZFUl9SRUFESU5FU1NfRkFJTEVEJykKICAgIHJlcG9ydCA9IGpzb24ubG9hZHMocmF3KQogICAgbmVlZChyZXBvcnQuZ2V0KCdtb2RlJykgPT0gJ1JFQURfT05MWV9DSEVDS1BPSU5UX1JFQURJTkVTUycsICdSRU1PVEVfUkVQT1JUX0lOVkFMSUQnKQogICAgcHJpbnQoanNvbi5kdW1wcyhyZXBvcnQsIGluZGVudD0yLCBzb3J0X2tleXM9VHJ1ZSksIGZsdXNoPVRydWUpCiAgICBtaW5pbXVtID0gbWF4KDIwKjEwMjQqKjMsIDIqcmVwb3J0WydpbWFnZV9ieXRlcyddKzEwKjEwMjQqKjMpCiAgICBlbm91Z2ggPSBzaHV0aWwuZGlza191c2FnZShQYXRoLmhvbWUoKSkuZnJlZSA+PSBtaW5pbXVtIGFuZCByZXBvcnRbJ3NlcnZlcl9mcmVlX2J5dGVzJ10gPj0gbWluaW11bQogICAgcHJpbnQoJ0NIRUNLUE9JTlRfRElTS19IRUFEUk9PTT0nKygnUEFTUycgaWYgZW5vdWdoIGVsc2UgJ0lOU1VGRklDSUVOVCcpLCBmbHVzaD1UcnVlKQogICAgcHJpbnQoJ05FWFQ9UElOX0ZJTkFMX0VOQ1JZUFRFRF9DQVBUVVJFX0FORF9JU09MQVRFRF9SRVNUT1JFJywgZmx1c2g9VHJ1ZSkKICAgIHByaW50KCdDQVBUVVJFX0FORF9SRVNUT1JFPU5PVF9SVU4nLCBmbHVzaD1UcnVlKQoKZGVmIHNlbGZfdGVzdCgpOgogICAgYXNzZXJ0IG92ZXJsYXAoJy9hL2InLCcvYS9iL2MnKSBhbmQgbm90IG92ZXJsYXAoJy9hL2InLCcvYS9iYycpCiAgICBhc3NlcnQgbGVuKElNQUdFUykgPT0gNSBhbmQgbGVuKEFQUFMpID09IDMKICAgIGFzc2VydCBhbGwocmUuZnVsbG1hdGNoKHInc2hhMjU2OlthLWYwLTldezY0fScsIHgpIGZvciB4IGluIElNQUdFUy52YWx1ZXMoKSkKICAgIGFzc2VydCBsZW4oUkVDSVBJRU5UKSA9PSA0MAogICAgYXNzZXJ0IG5vdCBwcml2YXRlX21ldGFkYXRhKFBhdGgoJy9ub25leGlzdGVudC12NzktdGVzdC1wYXRoJykpLmdldCgncHJlc2VudCcpCiAgICBpbXBvcnQgdGVtcGZpbGUKICAgIHdpdGggdGVtcGZpbGUuVGVtcG9yYXJ5RGlyZWN0b3J5KCkgYXMgdG1wOgogICAgICAgIHA9UGF0aCh0bXApLyd0ZXN0JzsgcC53cml0ZV90ZXh0KCdmaXh0dXJlJyk7IHAuY2htb2QoMG82MDApCiAgICAgICAgYXNzZXJ0IHByaXZhdGVfbWV0YWRhdGEocClbJ3JlZ3VsYXInXSBhbmQgcHJpdmF0ZV9tZXRhZGF0YShwKVsncHJpdmF0ZSddCiAgICAgICAgcC5jaG1vZCgwbzY0NCk7IGFzc2VydCBub3QgcHJpdmF0ZV9tZXRhZGF0YShwKVsncHJpdmF0ZSddCiAgICAgICAgbGluaz1QYXRoKHRtcCkvJ2xpbmsnOyBsaW5rLnN5bWxpbmtfdG8ocCk7IGFzc2VydCBub3QgcHJpdmF0ZV9tZXRhZGF0YShsaW5rKVsncmVndWxhciddCiAgICBwcmludCgnU0VMRl9URVNUPVBBU1NfU0NPUEVfUElOU19PVkVSTEFQX0FORF9QUklWQVRFX01FVEFEQVRBJykKCgppZiBfX25hbWVfXyA9PSAnX19tYWluX18nOgogICAgdHJ5OgogICAgICAgIHJlcG9ydD1zZXJ2ZXIoKQogICAgICAgIHByaW50KCdERU1PX1JFQURJTkVTUz1QQVNTJyBpZiBub3QgcmVwb3J0WydibG9ja2VycyddIGVsc2UgJ0RFTU9fUkVBRElORVNTPUJMT0NLRUQnKQogICAgICAgIHByaW50KCdORVdfSU5WRU5UT1JZX1NIQTI1Nj0nK3JlcG9ydFsnaW52ZW50b3J5X3NoYTI1NiddKQogICAgICAgIHByaW50KCdBVkFJTEFCTEVfTUVNT1JZX0JZVEVTPScrc3RyKHJlcG9ydFsnc2VydmVyX2F2YWlsYWJsZV9tZW1vcnlfYnl0ZXMnXSkpCiAgICAgICAgcHJpbnQoJ1NFUlZFUl9GUkVFX0JZVEVTPScrc3RyKHJlcG9ydFsnc2VydmVyX2ZyZWVfYnl0ZXMnXSkpCiAgICAgICAgcHJpbnQoJ0JBQ0tVUF9JTUFHRV9CWVRFUz0nK3N0cihyZXBvcnRbJ2ltYWdlX2J5dGVzJ10pKQogICAgICAgIHByaW50KCdFTkNSWVBURURfQVJUSUZBQ1RfQ09VTlQ9JytzdHIocmVwb3J0WydleHBlY3RlZF9lbmNyeXB0ZWRfYXJ0aWZhY3RzJ10pKQogICAgICAgIHByaW50KCdXT1JLRk9SQ0VfVElNRVJTPScrJywnLmpvaW4ocmVwb3J0WydhY3RpdmVfdGltZXJzX3RvX3F1aWVzY2UnXSkpCiAgICAgICAgcHJpbnQoJ1JFQURJTkVTU19CTE9DS0VSX0NPREVTPScrJywnLmpvaW4ocmVwb3J0WydibG9ja2VycyddKSkKICAgICAgICBwcmludCgnREVNT19SRUFESU5FU1NfQ0hBTkdFUz1OT05FJykKICAgIGV4Y2VwdCAoSGFsdCxPU0Vycm9yLFZhbHVlRXJyb3IsS2V5RXJyb3IsVHlwZUVycm9yKSBhcyBlcnJvcjoKICAgICAgICByZWFzb249c3RyKGVycm9yKSBpZiBpc2luc3RhbmNlKGVycm9yLEhhbHQpIGFuZCByZS5mdWxsbWF0Y2gocidbQS1aMC05X10rJyxzdHIoZXJyb3IpKSBlbHNlICdSRUFESU5FU1NfTUVUQURBVEFfVU5BVkFJTEFCTEUnCiAgICAgICAgcHJpbnQoJ0ZBSUxFRF9TVEFHRT0nK1NUQUdFKQogICAgICAgIHByaW50KCdTVE9QPScrcmVhc29uKQogICAgICAgIHN5cy5leGl0KDIpCg=='
INVENTORY = None  # supplied external PIN from freshly checked read-only inventory
RECIPIENT = '484CF39CE37A02884497AD9C41A17102D2842ECE'
TIMERS = ['v79-g2-approved-task-worker.timer','v79-workforce-evening.timer','v79-workforce-morning.timer']
APPS = ['v79-hub','v79-tiquet-manager','v79-business-agent']
DBS = ['v79-hub-postgres','tiquet-postgres']
STOP_ORDER = ['v79-business-agent','v79-tiquet-manager','v79-hub']
ROOT = Path('/home/firelion/.v79-release-checkpoints')
REMOTE_RE = r'/home/firelion/\.v79-release-checkpoints/release-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}'
SSH = ['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','firelion@192.168.100.163']
STAGE = 'START'
class Halt(Exception): pass
def need(ok, code):
    if not ok: raise Halt(code)
def phase(value):
    global STAGE
    STAGE=value
    print('PHASE='+value,flush=True)
def call(args, data=None, timeout=60):
    try:
        p=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired): raise Halt('COMMAND_UNAVAILABLE_OR_TIMEOUT') from None
    need(p.returncode==0,'COMMAND_FAILED_NO_SECRET_OUTPUT')
    return p.stdout
def jcall(args): return json.loads(call(args))
def inspect(name): return jcall(['docker','inspect',name])[0]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def private_dir(path, create=False):
    if create:
        try:path.mkdir(mode=0o700)
        except FileExistsError:pass
    st=path.lstat()
    need(stat.S_ISDIR(st.st_mode) and st.st_uid==os.getuid() and
         stat.S_IMODE(st.st_mode)==0o700,'PRIVATE_DIRECTORY_UNSAFE')
def write_new(path,raw):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(d)
    finally:os.close(d)
def write_json(path,value):write_new(path,(json.dumps(value,sort_keys=True,indent=2)+'\n').encode())
def read_private(path):
    st=path.lstat()
    need(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and
         not st.st_mode&0o077 and st.st_size<2*1024**2,'PRIVATE_FILE_UNSAFE')
    return json.loads(path.read_bytes())
def fingerprint(row):
    return {'image':row['Image'],'config':row['Config'], 'host':row['HostConfig'],
            'mounts':sorted(row.get('Mounts',[]),key=lambda m:m['Destination']),
            'networks':sorted(row.get('NetworkSettings',{}).get('Networks',{}))}
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def load_readiness():
    m=types.ModuleType('v79_step2_readiness')
    exec(compile(base64.b64decode(READINESS_B64),'embedded-readiness','exec'),m.__dict__)
    return m
def server_guard():
    need(socket.gethostname()=='v79sl' and Path.home()==Path('/home/firelion') and os.getuid()!=0,'WRONG_SERVER_USER')
    os.umask(0o077)
    load_readiness().local_docker('v79sl')
def validate_directory(text):
    need(bool(re.fullmatch(REMOTE_RE,text)),'INVALID_CHECKPOINT_DIRECTORY')
    p=Path(text);private_dir(p);return p
def lock_operation():
    p=Path.home()/'.v79-portfolio-rollout.lock'
    need(p.is_file() and not p.is_symlink(),'RELEASE_LOCK_MISSING_OR_UNSAFE')
    f=p.open('rb')
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:f.close();raise Halt('OTHER_RELEASE_OPERATION_RUNNING')
    return f
def env(row):return dict(x.split('=',1) for x in row['Config'].get('Env',[]) if '=' in x)
def price_equivalent(rendered,live):return rendered==live or rendered==live.replace('$','$$')
def environment_matches(container,key,rendered,live):
    if container in ('v79-tiquet-manager','tiquet-postgres') and key in (
            'PLAN_PRICE_STARTER','PLAN_PRICE_PRO','PLAN_PRICE_ENTERPRISE'):
        return price_equivalent(str(rendered),live)
    return str(rendered)==live
def build_models(rows):
    models={};inputs={};price_inputs={}
    # The database shares the Tiquet Compose chain. Supply the same frozen
    # interpolation values when rendering every service in that project.
    for plan in ('STARTER','PRO','ENTERPRISE'):
        value=env(rows['v79-tiquet-manager']).get('PLAN_PRICE_'+plan)
        need(bool(value),'FROZEN_PRICE_SOURCE_UNAVAILABLE')
        price_inputs['V79_P1_FROZEN_PLAN_PRICE_'+plan]=value
    for name,row in rows.items():
        labels=row['Config']['Labels'];directory=labels['com.docker.compose.project.working_dir']
        files=labels['com.docker.compose.project.config_files'].split(',')
        args=['docker','compose','--project-name',labels['com.docker.compose.project'],'--project-directory',directory]
        for p in files:
            inputs[p]=Path(p).read_bytes();args+=['--file',p]
        dotenv=Path(directory)/'.env'
        if dotenv.is_file() and not dotenv.is_symlink():inputs[str(dotenv)]=dotenv.read_bytes()
        e={**os.environ,**price_inputs}
        p=subprocess.run(args+['config','--format','json'],env=e,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60)
        need(p.returncode==0,'COMPOSE_RENDER_FAILED')
        model=json.loads(p.stdout);spec=model['services'][labels['com.docker.compose.service']]
        expected=env(row)
        for k,v in (spec.get('environment') or {}).items():
            need(k in expected,'COMPOSE_ENV_KEY_MISSING_FROM_LIVE')
            match=environment_matches(name,k,v,expected[k])
            if not match:
                print('COMPOSE_DIFFERING_SERVICE='+name,flush=True)
                print('COMPOSE_DIFFERING_KEY='+(k if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',k) else 'INVALID_ENVIRONMENT_KEY'),flush=True)
            need(match,'NONPRICE_COMPOSE_ENVIRONMENT_DRIFT')
        # Decoded engine values are authoritative. Do not use this record as
        # direct Compose input: it requires the isolated recovery codec.
        spec['environment']=expected
        spec['image']=row['Image']
        spec.pop('build',None)
        models[name]={'project':labels['com.docker.compose.project'],'service':labels['com.docker.compose.service'],
                      'model':model,'format':'decoded-engine-values-requires-recovery-codec'}
    need(sum(map(len,inputs.values()))<32*1024**2,'CONFIGURATION_INPUTS_TOO_LARGE')
    return models,inputs,price_inputs
def host_paths(report):
    paths=list(report['host_state_metadata'])
    paths+=['.config/systemd/user/'+n for n in report['workforce_unit_files']]
    for rel in paths:
        p=Path.home()/rel
        need(p.exists() and not p.is_symlink(),'HOST_STATE_SYMLINK_OR_MISSING')
        if p.is_dir():
            for root,dirs,files in os.walk(p,followlinks=False):
                for name in dirs+files:
                    st=(Path(root)/name).lstat()
                    need(stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode),'HOST_STATE_SPECIAL_OR_LINK_REQUIRES_REVIEW')
    return paths
def config_archive(rows,models,inputs,prices):
    content={'runtime-protected.json':json.dumps(rows,sort_keys=True).encode(),
             'decoded-service-models.json':json.dumps(models,sort_keys=True).encode(),
             'input-map.json':json.dumps({str(i):p for i,p in enumerate(inputs)},sort_keys=True).encode(),
             'frozen-price-inputs.json':json.dumps(prices,sort_keys=True).encode()}
    content.update({'config/'+str(i):b for i,b in enumerate(inputs.values())})
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w') as t:
        for name,data in content.items():
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600;t.addfile(info,io.BytesIO(data))
    return buf.getvalue()
def encrypt_args(keyring):
    return ['gpg','--homedir',str(keyring),'--batch','--quiet','--trust-model','always',
            '--compress-algo','ZIP','--compress-level','1','--encrypt','--recipient',RECIPIENT]
def encrypted_stream(producer_args,target,keyring,timeout):
    producer=encryptor=None
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:
        try:
            producer=subprocess.Popen(producer_args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            encryptor=subprocess.Popen(encrypt_args(keyring),stdin=producer.stdout,stdout=output,stderr=subprocess.DEVNULL)
            producer.stdout.close()
            need(encryptor.wait(timeout=timeout)==0,'ENCRYPTION_FAILED')
            need(producer.wait(timeout=15)==0,'CAPTURE_PRODUCER_FAILED')
            output.flush();os.fsync(output.fileno())
        finally:
            if producer and producer.stdout:producer.stdout.close()
            for p in (producer,encryptor):
                if p:
                    if p.poll() is None:p.kill()
                    p.wait()
    need(target.stat().st_size>64,'ENCRYPTED_ARTIFACT_EMPTY')
def encrypted_bytes(raw,target,keyring,timeout):
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        p=subprocess.run(encrypt_args(keyring),input=raw,stdout=f,stderr=subprocess.DEVNULL,timeout=timeout)
        need(p.returncode==0,'CONFIG_ENCRYPTION_FAILED');f.flush();os.fsync(f.fileno())
    need(target.stat().st_size>64,'ENCRYPTED_ARTIFACT_EMPTY')
def validate_journal(j):
    need(set(j['apps'])==set(APPS) and j['timers']==TIMERS,'RESUME_JOURNAL_SCOPE_INVALID')
    for n,p in j['apps'].items():
        need(re.fullmatch('[a-f0-9]{64}',p['id']) and re.fullmatch('sha256:[a-f0-9]{64}',p['image']) and
             re.fullmatch('[a-f0-9]{64}',p['fingerprint']),'RESUME_JOURNAL_IDENTITY_INVALID')
def wait_healthy(name,pin,timeout=180):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        row=inspect(pin['id'])
        need(row['Name']=='/'+name and row['Image']==pin['image'] and digest(fingerprint(row))==pin['fingerprint'],'ORIGINAL_RUNTIME_IDENTITY_CHANGED')
        if row['State'].get('Running') and row['State'].get('Health',{}).get('Status')=='healthy':return
        need(row['State'].get('Status') not in ('dead','removing'),'ORIGINAL_CONTAINER_CANNOT_RESUME')
        time.sleep(2)
    raise Halt('ORIGINAL_HEALTH_NOT_RESTORED')
def restore_originals(j, paused):
    validate_journal(j);failed=[]
    for name in APPS:
        pin=j['apps'][name]
        try:
            row=inspect(pin['id'])
            need(row['Name']=='/'+name and row['Image']==pin['image'] and digest(fingerprint(row))==pin['fingerprint'],'ORIGINAL_RUNTIME_IDENTITY_CHANGED')
            if not row['State'].get('Running'):call(['docker','start',pin['id']])
            wait_healthy(name,pin)
            print('RESUMED='+name+'_SAME_ID_HEALTHY',flush=True)
        except BaseException:failed.append(name)
    if failed:
        print('RESUME_FAILED_APPS='+','.join(failed),flush=True)
        raise Halt('APPS_REQUIRE_MANUAL_RESUME_TIMERS_HELD')
    if paused:
        call(['systemctl','--user','start',*j['timers']])
        for unit in j['timers']:need(call(['systemctl','--user','is-active',unit]).decode().strip()=='active','TIMER_RESUME_NOT_PROVEN')
        print('TIMERS=ORIGINALLY_ACTIVE_RESUMED',flush=True)
def timer_drain():
    deadline=time.monotonic()+120
    units=['v79-g2-approved-task-worker.service','v79-workforce-briefing@morning.service','v79-workforce-briefing@evening.service']
    while time.monotonic()<deadline:
        busy=False
        for unit in units:
            p=call(['systemctl','--user','show',unit,'--value','-p','ActiveState']).decode().strip()
            busy=busy or p in ('active','activating','deactivating','reloading')
        if not busy:return
        time.sleep(2)
    raise Halt('ACTIVE_WORKFORCE_JOB_NOT_DRAINED')
def capture_server(directory):
    server_guard();run=validate_directory(directory)
    need(Path(__file__).resolve()==run/'runner.py','PERSISTED_RUNNER_REQUIRED')
    operation_lock=lock_operation()
    try:
        phase('RECHECK_APPROVED_INVENTORY')
        report=load_readiness().server()
        # The embedded probe sees our already-held release lock. Only that
        # specific finding is expected; a second owner cannot hold our flock.
        blockers=[b for b in report['blockers'] if b!='OTHER_RELEASE_OPERATION_RUNNING']
        need(report['inventory_sha256']==INVENTORY and not blockers and
             report['active_timers_to_quiesce']==TIMERS,'READINESS_CHANGED_NO_PAUSE')
        need(report['server_free_bytes']>=2*report['image_bytes']+10*1024**3 and
             report['server_available_memory_bytes']>=1500*1024**2,'SERVER_RESOURCE_HEADROOM_CHANGED')
        names=call(['docker','ps','--all','--format','{{.Names}}']).decode().splitlines()
        before={r['Name'].lstrip('/'):r for r in jcall(['docker','inspect',*names])}
        rows={n:before[n] for n in report['pins']}
        phase('VALIDATE_CURRENT_COMPOSE_MODELS_AND_FROZEN_PRICES')
        models,inputs,prices=build_models(rows)
        paths=host_paths(report)
        keyring=run/'gnupg';private_dir(keyring)
        keys=call(['gpg','--homedir',str(keyring),'--batch','--with-colons','--fingerprint',RECIPIENT]).decode()
        need('fpr:::::::::'+RECIPIENT+':' in keys,'PUBLIC_RECOVERY_KEY_CHANGED')
        cp=run/'checkpoint';private_dir(cp,create=True)
        phase('ENCRYPT_FIVE_PINNED_IMAGES_BEFORE_PAUSE')
        encrypted_stream(['docker','save',*sorted({r['Image'] for r in rows.values()})],cp/'protected-images.tar.gpg',keyring,1800)
        # Identity/config recheck before any pause, including environment values.
        recheck=load_readiness().server()
        need(recheck['inventory_sha256']==INVENTORY and
             not [b for b in recheck['blockers'] if b!='OTHER_RELEASE_OPERATION_RUNNING'],
             'INVENTORY_CHANGED_DURING_IMAGE_EXPORT')
        for n,r in rows.items():need(fingerprint(inspect(n))==fingerprint(r),'RUNTIME_CHANGED_BEFORE_PAUSE')
        journal={'apps':{n:{'id':rows[n]['Id'],'image':rows[n]['Image'],'fingerprint':digest(fingerprint(rows[n]))} for n in APPS},
                 'timers':TIMERS,'runner_sha256':sha(Path(__file__))}
        validate_journal(journal);write_json(run/'resume.json',journal)
        paused=False;pause_started=None
        signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(Halt('CAPTURE_INTERRUPTED')))
        try:
            phase('PAUSE_THREE_TIMERS_AND_DRAIN_CURRENT_JOBS')
            paused=True;call(['systemctl','--user','stop',*TIMERS]);timer_drain()
            pause_started=time.monotonic()
            phase('PAUSE_ONLY_THREE_PINNED_APPS_DATABASES_STAY_RUNNING')
            for n in STOP_ORDER:call(['docker','stop','--time','60',rows[n]['Id']],timeout=80)
            def remaining():
                seconds=600-(time.monotonic()-pause_started)
                need(seconds>0,'PAUSE_BUDGET_EXCEEDED');return max(1,min(240,seconds))
            phase('CAPTURE_DATABASES_MOUNTS_AND_PRIVATE_HOST_STATE')
            for db in DBS:
                # Refuse another active client while the intended application is stopped.
                count=call(['docker','exec',rows[db]['Id'],'sh','-c',
                    'exec psql -X -At -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}" -c "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type=\x27client backend\x27"']).decode().strip()
                need(count=='0','OTHER_DATABASE_CLIENT_REQUIRES_REVIEW')
                encrypted_stream(['docker','exec',rows[db]['Id'],'sh','-c',
                    'exec pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}" -Fc'],cp/(db+'.dump.gpg'),keyring,remaining())
            mount_map=[]
            for n in APPS:
                for index,m in enumerate(rows[n].get('Mounts',[])):
                    filename=n+'-mount-'+str(index)+'.tar.gpg'
                    encrypted_stream(['docker','cp',rows[n]['Id']+':'+m['Destination'],'-'],cp/filename,keyring,remaining())
                    mount_map.append({'container':n,'destination':m['Destination'],'artifact':filename})
            encrypted_stream(['tar','--format=pax','--numeric-owner','-C',str(Path.home()),'-cf','-','--',*paths],cp/'private-host-state.tar.gpg',keyring,remaining())
            encrypted_bytes(config_archive(rows,models,inputs,prices),cp/'runtime-and-config.tar.gpg',keyring,remaining())
            need(all(Path(p).read_bytes()==b for p,b in inputs.items()),'CONFIG_INPUT_CHANGED_DURING_CAPTURE')
            remaining()
        finally:
            phase('RESUME_SAME_APP_IDS_AND_ORIGINAL_TIMERS')
            restore_originals(journal,paused)
        names_after=call(['docker','ps','--all','--format','{{.Names}}']).decode().splitlines()
        need(set(names_after)==set(before),'CONTAINER_INVENTORY_CHANGED_AFTER_CAPTURE')
        for n,r in before.items():
            now=inspect(r['Id'])
            need(now['Id']==r['Id'] and now['Image']==r['Image'] and fingerprint(now)==fingerprint(r),'CONTAINER_RUNTIME_CHANGED_AFTER_CAPTURE')
            if n not in APPS:
                need(now['State']['Status']==r['State']['Status'] and now['State'].get('StartedAt')==r['State'].get('StartedAt'),'UNRELATED_CONTAINER_RESTARTED')
        files=[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(cp.iterdir())]
        need(len(files)==15 and all(p['name'].endswith('.gpg') and p['bytes']>64 for p in files),'CAPTURE_ARTIFACT_SET_INCOMPLETE')
        manifest={'audit':'V79_RELEASE_WINDOW_CHECKPOINT_V1','state':'CAPTURED_NOT_RESTORE_TESTED',
                  'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'inventory_sha256':INVENTORY,'images':{n:r['Image'] for n,r in rows.items()},
                  'mount_artifacts':mount_map,'host_paths':paths,'files':files,
                  'recipient_fingerprint':RECIPIENT,'apps_resumed_same_ids':True,
                  'source_receipt':'owner-authorized-hardened-pair-prerequisites-20261025',
                  'frozen_price_inputs':'encrypted-runtime-and-config.tar.gpg',
                  'model_format':'decoded-engine-values-requires-recovery-codec',
                  'pause_seconds':round(time.monotonic()-pause_started,1),
                  'restore_tested':False,'release_decision':'HOLD','application_rollback_rehearsed':False}
        write_json(cp/'manifest.json',manifest)
        phase('CAPTURE_COMPLETE_SAME_IDS_HEALTHY_OFFHOST_VERIFICATION_REQUIRED')
    finally:operation_lock.close()
def resume_server(directory):
    server_guard();run=validate_directory(directory)
    lock=lock_operation()
    try:
        j=read_private(run/'resume.json')
        need(j['runner_sha256']==sha(Path(__file__)),'RECOVERY_RUNNER_CHANGED')
        restore_originals(j,True)
        print('RECOVERY=SAME_IDS_AND_TIMERS_RESUMED',flush=True)
    finally:lock.close()
def decrypt_validate(path):
    p=subprocess.Popen(['gpg','--batch','--quiet','--decrypt',str(path)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    h=hashlib.sha256();count=0
    try:
        for b in iter(lambda:p.stdout.read(1024*1024),b''):h.update(b);count+=len(b)
        need(p.wait(timeout=30)==0 and count>0,'OFFHOST_DECRYPT_VALIDATION_FAILED')
    finally:
        if p.stdout:p.stdout.close()
        if p.poll() is None:p.kill()
        p.wait()
    return {'plaintext_sha256':h.hexdigest(),'plaintext_bytes':count}
def remote_file(directory,filename):
    need(re.fullmatch(REMOTE_RE,directory) and re.fullmatch(r'[A-Za-z0-9_.-]+',filename),'REMOTE_PATH_INVALID')
    return directory+'/checkpoint/'+filename
def verify_offhost(directory):
    phase('TRANSFER_CIPHERTEXT_TO_ACER_AND_VERIFY_DECRYPTION')
    parent=Path.home()/'V79-Portfolio-Checkpoints'
    if parent.exists():
        need(parent.is_dir() and not parent.is_symlink() and parent.stat().st_uid==os.getuid(),'OFFHOST_PARENT_UNSAFE')
    else:private_dir(parent,create=True)
    dest=parent/Path(directory).name
    private_dir(dest,create=True)
    remote=shlex.quote(remote_file(directory,'manifest.json'))
    raw=call([*SSH,'cat -- '+remote])
    manifest=json.loads(raw)
    need(manifest.get('audit')=='V79_RELEASE_WINDOW_CHECKPOINT_V1' and manifest.get('inventory_sha256')==INVENTORY and
         len(manifest.get('files',[]))==15,'OFFHOST_MANIFEST_UNEXPECTED')
    need(manifest.get('images')==load_readiness().IMAGES,'OFFHOST_IMAGE_PINS_UNEXPECTED')
    expected={'protected-images.tar.gpg','runtime-and-config.tar.gpg','private-host-state.tar.gpg',
              'v79-hub-postgres.dump.gpg','tiquet-postgres.dump.gpg'}
    expected.update(n+'-mount-'+str(i)+'.tar.gpg' for n,count in
                    [('v79-hub',7),('v79-tiquet-manager',2),('v79-business-agent',1)] for i in range(count))
    need({x['name'] for x in manifest['files']}==expected,'OFFHOST_ARTIFACT_SET_UNEXPECTED')
    if (dest/'manifest.json').exists():need((dest/'manifest.json').read_bytes()==raw,'EXISTING_MANIFEST_CONFLICT')
    else:write_new(dest/'manifest.json',raw)
    verified=[]
    for entry in manifest['files']:
        name=entry['name'];need(re.fullmatch(r'[A-Za-z0-9_.-]+\.gpg',name),'ARTIFACT_NAME_INVALID')
        need(re.fullmatch('[a-f0-9]{64}',entry['sha256']) and isinstance(entry['bytes'],int) and entry['bytes']>64,'ARTIFACT_METADATA_INVALID')
        target=dest/name
        if target.exists():
            need(target.is_file() and not target.is_symlink() and target.stat().st_uid==os.getuid() and not target.stat().st_mode&0o077,'EXISTING_ARTIFACT_UNSAFE')
            need(target.stat().st_size==entry['bytes'] and sha(target)==entry['sha256'],'EXISTING_ARTIFACT_CONFLICT')
        else:
            part=dest/(name+'.part')
            offset=0
            if part.exists() or part.is_symlink():
                st=part.lstat()
                need(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and not st.st_mode&0o077 and
                     st.st_size<=entry['bytes'],'PARTIAL_TRANSFER_UNSAFE')
                offset=st.st_size
                fd=os.open(part,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW)
            else:
                fd=os.open(part,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as f:
                if offset<entry['bytes']:
                    command='tail -c +'+str(offset+1)+' -- '+shlex.quote(remote_file(directory,name))
                    p=subprocess.run([*SSH,command],stdout=f,stderr=subprocess.DEVNULL,timeout=3600)
                    need(p.returncode==0,'OFFHOST_TRANSFER_FAILED')
                f.flush();os.fsync(f.fileno())
            need(part.stat().st_size==entry['bytes'] and sha(part)==entry['sha256'],'OFFHOST_CIPHERTEXT_HASH_MISMATCH')
            os.link(part,target);part.unlink()
        result=decrypt_validate(target);verified.append({'name':name,**result})
        print('OFFHOST_ARTIFACT_VERIFIED='+name,flush=True)
    receipt={'audit':'V79_RELEASE_WINDOW_OFFHOST_CUSTODY_V1','verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'manifest_sha256':hashlib.sha256(raw).hexdigest(),'files':verified,'restore_tested':False}
    out=dest/('offhost-verified-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
    write_json(out,receipt)
    print('OFFHOST_CHECKPOINT='+str(dest),flush=True)
    print('OFFHOST_CIPHERTEXT_AND_DECRYPT=PASS_15_OF_15',flush=True)
    print('EXISTING_RECOVERY_PROOF=RETAINED_NOT_RERUN',flush=True)
    print('NEW_CAPTURE_RESTORE_REHEARSED=FALSE',flush=True)
    return dest
def monitor(directory):
    need(re.fullmatch(REMOTE_RE,directory),'INVALID_CHECKPOINT_DIRECTORY')
    phase('MONITOR_DETACHED_SERVER_CAPTURE')
    command='python3 -B - '+shlex.quote(directory)
    probe=b'''import json,sys\nfrom pathlib import Path\np=Path(sys.argv[1]);s=(p/'progress.log').read_text() if (p/'progress.log').exists() else '';x=(p/'exit-code').read_text().strip() if (p/'exit-code').exists() else None\nprint(json.dumps({'progress':s[-20000:],'exit':x}))\n'''
    seen=''
    while True:
        data=json.loads(call([*SSH,command],data=probe))
        progress=data['progress']
        for line in progress[len(seen):].splitlines():
            need(bool(re.fullmatch(r'[A-Z_]+=[A-Za-z0-9_,./:-]+',line)),'REMOTE_PROGRESS_UNSAFE')
            print(line,flush=True)
        seen=progress
        if data['exit'] is not None:
            need(data['exit']=='0','CAPTURE_FAILED_REVIEW_STATUS_USE_RESUME_IF_NEEDED')
            return verify_offhost(directory)
        time.sleep(5)
def acer_guard():
    need(socket.gethostname()=='firelion-Aspire-A315-51' and os.getuid()!=0,'RUN_ON_NONROOT_ACER')
    os.umask(0o077);load_readiness().local_docker(socket.gethostname())
def start_capture():
    acer_guard();phase('VERIFY_ACER_RECOVERY_KEY_WITH_REAL_ROUNDTRIP')
    sample=os.urandom(48)
    encrypted=call(['gpg','--batch','--quiet','--trust-model','always','--encrypt','--recipient',RECIPIENT],data=sample)
    need(call(['gpg','--batch','--quiet','--decrypt'],data=encrypted)==sample,'ACER_KEY_DECRYPT_ROUNDTRIP_FAILED')
    need(shutil.disk_usage(Path.home()).free>20*1024**3,'ACER_DISK_HEADROOM_CHANGED')
    public=call(['gpg','--batch','--export',RECIPIENT]);need(public,'PUBLIC_KEY_EXPORT_FAILED')
    # Install only the reviewed runner and public key in a new private directory.
    payload={'source':base64.b64encode(Path(__file__).read_bytes()).decode(),
             'sha256':sha(Path(__file__)),'public':base64.b64encode(public).decode()}
    bootstrap=r'''import base64,datetime,hashlib,json,os,secrets,socket,stat,subprocess,sys
from pathlib import Path
assert socket.gethostname()=='v79sl' and os.getuid()!=0
os.umask(0o077);p=json.load(sys.stdin);root=Path.home()/'.v79-release-checkpoints'
if not root.exists():root.mkdir(mode=0o700)
s=root.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700
run=root/('release-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4));run.mkdir(mode=0o700)
raw=base64.b64decode(p['source']);assert hashlib.sha256(raw).hexdigest()==p['sha256']
f=os.open(run/'runner.py',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(f,'wb') as out:out.write(raw)
keyring=run/'gnupg';keyring.mkdir(mode=0o700)
c=subprocess.run(['gpg','--homedir',str(keyring),'--batch','--quiet','--import'],input=base64.b64decode(p['public']),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
assert c.returncode==0
print(str(run))
'''
    # Program and JSON use separate channels through a base64-safe stdin loader.
    command='python3 -c '+shlex.quote(bootstrap)
    directory=call([*SSH,command],data=json.dumps(payload).encode()).decode().strip()
    need(re.fullmatch(REMOTE_RE,directory),'BOOTSTRAP_DIRECTORY_INVALID')
    print('SERVER_CHECKPOINT_DIRECTORY='+directory,flush=True)
    pointer=Path(__file__).resolve().parent/'SERVER_CAPTURE.json'
    write_json(pointer,{'directory':directory,'runner_sha256':sha(Path(__file__)),'inventory_sha256':INVENTORY})
    launch=shlex.join(['python3','-B','-u',directory+'/runner.py','--server-capture',directory,
                       '--inventory-sha256',INVENTORY])
    call([*SSH,'umask 077; nohup '+launch+' > '+shlex.quote(directory+'/progress.log')+' 2>&1 < /dev/null &'])
    print('CAPTURE=DETACHED_FROM_SSH_MONITOR',flush=True)
    return monitor(directory)
def server_entry(directory):
    run=validate_directory(directory);code=1
    try:
        capture_server(directory);code=0
    except BaseException as error:
        safe=str(error) if isinstance(error,Halt) and re.fullmatch('[A-Z0-9_]+',str(error)) else 'CAPTURE_INCOMPLETE_REVIEW_REQUIRED'
        print('FAILED_STAGE='+STAGE,flush=True);print('STOP='+safe,flush=True)
    finally:write_new(run/'exit-code',str(code).encode())
    return code
def self_test():
    # Extended tests are built into the same downloadable file below.
    import unittest
    import contextlib
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(CaptureTests)
    transcript=io.StringIO()
    with contextlib.redirect_stdout(transcript):
        result=unittest.TextTestRunner(stream=transcript,verbosity=1).run(suite)
    if not result.wasSuccessful():print(transcript.getvalue(),flush=True)
    need(result.wasSuccessful(),'SELF_TEST_FAILED')
    print('SELF_TEST=PASS_'+str(result.testsRun)+'_TESTS',flush=True)

import unittest
from unittest.mock import patch

class CaptureTests(unittest.TestCase):
    def row(self,name='v79-hub',running=False):
        return {'Name':'/'+name,'Id':'a'*64,'Image':'sha256:'+'b'*64,
                'Config':{'Env':['PRICE=$150'],'Cmd':['node','server']},'HostConfig':{'Binds':['/a:/b:ro']},
                'Mounts':[{'Destination':'/b','Source':'/a','RW':False,'Type':'bind'}],
                'NetworkSettings':{'Networks':{'private':{}}},'State':{'Running':running,'Health':{'Status':'healthy'}}}
    def journal(self):
        return {'apps':{n:{'id':'a'*64,'image':'sha256:'+'b'*64,'fingerprint':digest(fingerprint(self.row(n)))} for n in APPS},'timers':TIMERS}
    def test_scope_is_current_five_images_three_apps(self):
        r=load_readiness()
        self.assertEqual(set(r.IMAGES),set(APPS+DBS))
        self.assertEqual(r.IMAGES['v79-hub'],'sha256:66caa099adf1321b72a90b22f8125981e5a6d99b5920cebae0454541cccd9fa7')
    def test_directory_scope_rejects_other_paths(self):
        for p in ['/tmp/test','/home/firelion/.v79-release-checkpoints/../x','/home/firelion/.v79-release-checkpoints/release-bad']:
            self.assertIsNone(re.fullmatch(REMOTE_RE,p))
        self.assertIsNotNone(re.fullmatch(REMOTE_RE,'/home/firelion/.v79-release-checkpoints/release-20261021T120000Z-aabbccdd'))
    def test_price_codec_accepts_exact_and_only_dollar_escape(self):
        self.assertTrue(price_equivalent('$150','$150'))
        self.assertTrue(price_equivalent('$$150','$150'))
        self.assertFalse(price_equivalent('$$151','$150'))
        self.assertFalse(price_equivalent('$$$$150','$150'))
    def test_price_equivalence_is_limited_to_two_tiquet_services(self):
        for service in ('v79-tiquet-manager','tiquet-postgres'):
            for key in ('PLAN_PRICE_STARTER','PLAN_PRICE_PRO','PLAN_PRICE_ENTERPRISE'):
                self.assertTrue(environment_matches(service,key,'$$150','$150'))
                self.assertFalse(environment_matches(service,key,'$$151','$150'))
        for service in ('v79-hub','v79-business-agent','v79-hub-postgres'):
            self.assertFalse(environment_matches(service,'PLAN_PRICE_STARTER','$$150','$150'))
    def test_database_nonprice_fields_remain_exact(self):
        for key in ('POSTGRES_PASSWORD','POSTGRES_DB','OTHER_SETTING'):
            self.assertTrue(environment_matches('tiquet-postgres',key,'same','same'))
            self.assertFalse(environment_matches('tiquet-postgres',key,'$$value','$value'))
    def build_tiquet_database_model(self,wrong_price=False,wrong_secret=False):
        import contextlib
        with tempfile.TemporaryDirectory() as d:
            compose=Path(d)/'compose.yml';compose.write_text('synthetic fixture')
            row=self.row('tiquet-postgres',True)
            row['Config']['Labels']={'com.docker.compose.project.working_dir':d,
                'com.docker.compose.project.config_files':str(compose),
                'com.docker.compose.project':'fixture','com.docker.compose.service':'db'}
            row['Config']['Env']=['PLAN_PRICE_STARTER=$150','PLAN_PRICE_PRO=$350',
                                  'PLAN_PRICE_ENTERPRISE=$900','POSTGRES_PASSWORD=synthetic-only']
            declared={'PLAN_PRICE_STARTER':'$$151' if wrong_price else '$$150',
                      'PLAN_PRICE_PRO':'$$350','PLAN_PRICE_ENTERPRISE':'$$900',
                      'POSTGRES_PASSWORD':'changed-synthetic-only' if wrong_secret else 'synthetic-only'}
            result=types.SimpleNamespace(returncode=0,stdout=json.dumps({'services':{'db':{'environment':declared}}}).encode())
            log=io.StringIO()
            app=json.loads(json.dumps(row));app['Name']='/v79-tiquet-manager'
            rows={'tiquet-postgres':row,'v79-tiquet-manager':app}
            with patch('subprocess.run',return_value=result) as rendered,contextlib.redirect_stdout(log):
                if wrong_price or wrong_secret:
                    with self.assertRaises(Halt):build_models(rows)
                    self.assertNotIn('synthetic-only',log.getvalue())
                    self.assertNotIn('$150',log.getvalue())
                else:
                    models,inputs,prices=build_models(rows)
                    self.assertEqual(models['tiquet-postgres']['model']['services']['db']['environment']['PLAN_PRICE_STARTER'],'$150')
                    self.assertEqual(prices,{'V79_P1_FROZEN_PLAN_PRICE_STARTER':'$150',
                        'V79_P1_FROZEN_PLAN_PRICE_PRO':'$350','V79_P1_FROZEN_PLAN_PRICE_ENTERPRISE':'$900'})
                    for rendered_call in rendered.call_args_list:
                        self.assertEqual(rendered_call.kwargs['env']['V79_P1_FROZEN_PLAN_PRICE_STARTER'],'$150')
                    self.assertEqual(inputs[str(compose)],b'synthetic fixture')
    def test_real_model_builder_accepts_database_price_serialization(self):
        self.build_tiquet_database_model()
    def test_real_model_builder_rejects_changed_database_price(self):
        self.build_tiquet_database_model(wrong_price=True)
    def test_real_model_builder_rejects_changed_database_password_without_logging(self):
        self.build_tiquet_database_model(wrong_secret=True)
    def test_fingerprint_ignores_health_but_detects_environment(self):
        a=self.row();b=json.loads(json.dumps(a));b['State']['Health']['Status']='starting'
        self.assertEqual(fingerprint(a),fingerprint(b))
        b['Config']['Env']=['PRICE=$151'];self.assertNotEqual(fingerprint(a),fingerprint(b))
    def test_fingerprint_detects_mount_permission_and_network(self):
        a=self.row();b=json.loads(json.dumps(a));b['Mounts'][0]['RW']=True
        self.assertNotEqual(fingerprint(a),fingerprint(b))
        b=self.row();b['NetworkSettings']['Networks']={'outside':{}}
        self.assertNotEqual(fingerprint(a),fingerprint(b))
    def test_journal_rejects_foreign_app_and_timer(self):
        j=self.journal();validate_journal(j)
        j['apps']['foreign']=j['apps']['v79-hub']
        with self.assertRaises(Halt):validate_journal(j)
        j=self.journal();j['timers']=['foreign.timer']
        with self.assertRaises(Halt):validate_journal(j)
    def test_journal_rejects_bad_identity(self):
        j=self.journal();j['apps']['v79-hub']['id']='../../bad'
        with self.assertRaises(Halt):validate_journal(j)
    def test_config_archive_contains_exact_frozen_inputs(self):
        raw=config_archive({'v79-hub':self.row()},{'test':{}},{'/safe/config':b'fixture'}, {'price':'$150'})
        with tarfile.open(fileobj=io.BytesIO(raw)) as t:
            self.assertEqual(json.load(t.extractfile('frozen-price-inputs.json')),{'price':'$150'})
            self.assertEqual(t.extractfile('config/0').read(),b'fixture')
            self.assertTrue(all(x.mode==0o600 and x.isfile() and not x.name.startswith('/') for x in t.getmembers()))
    def test_exclusive_private_write_rejects_collision(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x';write_new(p,b'fixture')
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
            with self.assertRaises(FileExistsError):write_new(p,b'changed')
            self.assertEqual(p.read_bytes(),b'fixture')
    def test_private_json_rejects_symlink_and_exposed_mode(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x';write_json(p,{'fixture':True});p.chmod(0o644)
            with self.assertRaises(Halt):read_private(p)
            p.chmod(0o600);q=Path(d)/'q';q.symlink_to(p)
            with self.assertRaises(Halt):read_private(q)
    def test_resume_starts_only_original_app_ids_before_timers(self):
        j=self.journal();calls=[]
        def command(a,**k):calls.append(a);return b'active\n'
        def lookup(i):
            # All fixture IDs are the same; caller's name check is exercised by
            # the per-iteration lookup side effect below.
            return self.row(next(names))
        names=iter(APPS)
        with patch(__name__+'.inspect',side_effect=lookup),patch(__name__+'.wait_healthy'),patch(__name__+'.call',side_effect=command):
            restore_originals(j,True)
        self.assertEqual([a[:2] for a in calls[:3]],[['docker','start']]*3)
        self.assertEqual(calls[3],['systemctl','--user','start',*TIMERS])
    def test_resume_failure_attempts_all_apps_and_holds_timers(self):
        j=self.journal();seen=[];calls=[]
        def lookup(i):
            name=APPS[len(seen)];seen.append(name)
            if name=='v79-hub':raise Halt('FIXTURE_FAILURE')
            return self.row(name)
        with patch(__name__+'.inspect',side_effect=lookup),patch(__name__+'.wait_healthy'),patch(__name__+'.call',side_effect=lambda a,**k:calls.append(a) or b''):
            with self.assertRaises(Halt):restore_originals(j,True)
        self.assertEqual(seen,APPS)
        self.assertFalse(any(a[:2]==['systemctl','--user'] for a in calls))
    def test_resume_does_not_start_changed_identity(self):
        j=self.journal();calls=[];names=iter(APPS)
        def lookup(i):
            r=self.row(next(names));r['Image']='sha256:'+'c'*64;return r
        with patch(__name__+'.inspect',side_effect=lookup),patch(__name__+'.call',side_effect=lambda a,**k:calls.append(a) or b''):
            with self.assertRaises(Halt):restore_originals(j,True)
        self.assertEqual(calls,[])
    def test_producer_failure_is_not_a_successful_encrypted_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'cipher'
            with patch(__name__+'.encrypt_args',return_value=['cat']):
                with self.assertRaises(Halt):
                    encrypted_stream(['sh','-c','printf fixture; exit 7'],p,Path(d),10)
    def test_encryption_failure_kills_producer(self):
        with tempfile.TemporaryDirectory() as d:
            with patch(__name__+'.encrypt_args',return_value=['sh','-c','exit 9']):
                with self.assertRaises(Halt):
                    encrypted_stream(['sh','-c','printf fixture'],Path(d)/'cipher',Path(d),10)
    def test_remote_path_rejects_shell_and_traversal(self):
        directory='/home/firelion/.v79-release-checkpoints/release-20261021T120000Z-aabbccdd'
        self.assertTrue(remote_file(directory,'manifest.json').endswith('/checkpoint/manifest.json'))
        for name in ['../x','x;id','$(id)','x\ny']:
            with self.assertRaises(Halt):remote_file(directory,name)

    def capture_fixture(self, fail_dump=False):
        import contextlib,copy
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'gnupg').mkdir(mode=0o700)
            write_new(root/'runner.py',b'fixture runner')
            rows={n:self.row(n,True) for n in APPS+DBS}
            for index,(n,r) in enumerate(rows.items()):
                r['Id']=format(index+1,'064x');r['State'].update({'Status':'running','StartedAt':'fixture'})
                count={'v79-hub':7,'v79-tiquet-manager':2,'v79-business-agent':1}.get(n,0)
                r['Mounts']=[{'Destination':'/mount/'+str(i),'Source':'/source/'+n+'/'+str(i),'RW':False,'Type':'bind'} for i in range(count)]
            actions=[];ready=types.SimpleNamespace(server=lambda:{'inventory_sha256':INVENTORY,
                'blockers':['OTHER_RELEASE_OPERATION_RUNNING'],'active_timers_to_quiesce':TIMERS,
                'pins':dict.fromkeys(rows),'server_free_bytes':100*1024**3,'image_bytes':4*1024**3,
                'server_available_memory_bytes':4*1024**3})
            def fake_call(args,**kwargs):
                actions.append(args)
                if args[:3]==['docker','ps','--all']:return ('\n'.join(rows)+'\n').encode()
                if args[0]=='gpg':return ('fpr:::::::::'+RECIPIENT+':\n').encode()
                if args[:2]==['docker','stop']:
                    r=next(r for r in rows.values() if r['Id']==args[-1]);r['State'].update({'Running':False,'Status':'exited'});return b''
                if args[:2]==['docker','start']:
                    r=next(r for r in rows.values() if r['Id']==args[-1]);r['State'].update({'Running':True,'Status':'running'});return b''
                if args[:2]==['docker','exec']:return b'0\n'
                if args[:3]==['systemctl','--user','is-active']:return b'active\n'
                return b''
            def lookup(name):return copy.deepcopy(rows[name] if name in rows else next(r for r in rows.values() if r['Id']==name))
            def stream(args,target,keyring,timeout):
                actions.append(['artifact',target.name])
                if fail_dump and target.name.endswith('.dump.gpg'):raise Halt('FIXTURE_DUMP_FAILURE')
                write_new(target,b'encrypted-fixture'*10)
            with contextlib.ExitStack() as stack:
                for name,value in [('server_guard',lambda:None),('validate_directory',lambda p:root),
                    ('lock_operation',lambda:open(os.devnull,'rb')),('load_readiness',lambda:ready),
                    ('call',fake_call),('jcall',lambda a:copy.deepcopy(list(rows.values()))),
                    ('inspect',lookup),('build_models',lambda r:({},{},{})),('host_paths',lambda r:[]),
                    ('timer_drain',lambda:None),('encrypted_stream',stream),
                    ('encrypted_bytes',lambda raw,target,keyring,timeout:write_new(target,b'cipher fixture'*10))]:
                    stack.enter_context(patch(__name__+'.'+name,side_effect=value))
                stack.enter_context(patch(__name__+'.__file__',str(root/'runner.py')))
                stack.enter_context(patch('signal.signal'))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                if fail_dump:
                    with self.assertRaises(Halt):capture_server(str(root))
                    self.assertFalse((root/'checkpoint/manifest.json').exists())
                else:
                    capture_server(str(root))
                    manifest=read_private(root/'checkpoint/manifest.json')
                    self.assertEqual(len(manifest['files']),15)
                    self.assertFalse(manifest['restore_tested'])
            self.assertTrue(all(r['State']['Running'] for r in rows.values()))
            stops=[a[-1] for a in actions if a[:2]==['docker','stop']]
            self.assertEqual(stops,[rows[n]['Id'] for n in STOP_ORDER])
            self.assertIn(['systemctl','--user','start',*TIMERS],actions)
            self.assertLess(actions.index(['artifact','protected-images.tar.gpg']),next(i for i,a in enumerate(actions) if a[:2]==['docker','stop']))
    def test_complete_capture_control_flow_preserves_ids_and_exact_artifact_set(self):
        self.capture_fixture()
    def test_interrupted_dump_resumes_apps_and_timers_without_manifest(self):
        self.capture_fixture(fail_dump=True)



def main():
    p=argparse.ArgumentParser(description=__doc__)
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--self-test',action='store_true')
    modes.add_argument('--capture',action='store_true')
    modes.add_argument('--server-capture')
    modes.add_argument('--monitor')
    modes.add_argument('--resume-server')
    p.add_argument('--inventory-sha256')
    a=p.parse_args()
    global INVENTORY
    if not a.self_test:
        need(isinstance(a.inventory_sha256,str) and bool(re.fullmatch(r'[0-9a-f]{64}',a.inventory_sha256)),
             'FRESH_EXTERNAL_INVENTORY_SHA256_REQUIRED')
        INVENTORY=a.inventory_sha256
    if a.self_test:self_test()
    elif a.capture:start_capture()
    elif a.server_capture:sys.exit(server_entry(a.server_capture))
    elif a.resume_server:resume_server(a.resume_server)
    elif a.monitor:acer_guard();monitor(a.monitor)
if __name__=='__main__':
    try:main()
    except BaseException as error:
        if isinstance(error,SystemExit):raise
        safe=str(error) if isinstance(error,Halt) and re.fullmatch('[A-Z0-9_]+',str(error)) else 'CHECKPOINT_INCOMPLETE_REVIEW_REQUIRED'
        print('FAILED_STAGE='+STAGE,flush=True);print('STOP='+safe,flush=True);sys.exit(1)
