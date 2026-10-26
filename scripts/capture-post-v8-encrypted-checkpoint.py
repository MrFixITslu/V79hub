#!/usr/bin/env python3
"""Fresh encrypted V79 checkpoint. Capture pauses only the three pinned apps and
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

READINESS_B64='IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJSZWFkLW9ubHkgY2hlY2twb2ludCByZWFkaW5lc3MuIE5ldmVyIHBhdXNlcywgY2FwdHVyZXMgb3IgcmVzdG9yZXMgcHJvZHVjdGlvbi4iIiIKaW1wb3J0IGFyZ3BhcnNlCmltcG9ydCBkYXRldGltZQppbXBvcnQgZmNudGwKaW1wb3J0IGhhc2hsaWIKaW1wb3J0IGpzb24KaW1wb3J0IG9zCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBvcnQgcmUKaW1wb3J0IHNodXRpbAppbXBvcnQgc29ja2V0CmltcG9ydCBzdGF0CmltcG9ydCBzdWJwcm9jZXNzCmltcG9ydCBzeXMKClJFQ0lQSUVOVCA9ICc0ODRDRjM5Q0UzN0EwMjg4NDQ5N0FEOUM0MUExNzEwMkQyODQyRUNFJwpBUFBTID0gKCd2NzktaHViJywgJ3Y3OS10aXF1ZXQtbWFuYWdlcicsICd2NzktYnVzaW5lc3MtYWdlbnQnKQpJTUFHRVMgPSB7CiAgICAndjc5LWh1Yic6ICdzaGEyNTY6NjZjYWEwOTlhZGYxMzIxYjcyYTkwYjIyZjgxMjU5ODFlNWE2ZDk5YjU5MjBjZWJhZTA0NTQ1NDFjY2NkOWZhNycsCiAgICAndjc5LXRpcXVldC1tYW5hZ2VyJzogJ3NoYTI1Njo4YTVlMTViMTU3MzJjZWQwM2U3N2Y0Y2VlYmIwMTlkOGVhMTEzODFiMTQ2NDU2NTM5MzNlOGU4MTQ0YTEzY2MwJywKICAgICd2NzktYnVzaW5lc3MtYWdlbnQnOiAnc2hhMjU2OjFiYTI2ZDIyMDU1YjUzZGM5OTI3ODY3M2I3NzRlNDgwMDA2MTQzZjgwMjIyNTA5YTMyNTVlNzVkNTQ1MjZmNGInLAogICAgJ3Y3OS1odWItcG9zdGdyZXMnOiAnc2hhMjU2OmIwZjk1NjBhMmRlMDgzZTJjYzczODJlNzVmODA4YzczODFhMzI4NTJhN2VjNDkxMTdkZWVkYjMwMGU1NTJiMjQnLAogICAgJ3RpcXVldC1wb3N0Z3Jlcyc6ICdzaGEyNTY6Y2Y3OGU3NjY4M2I5Y2E4YzU3MzNjYmJkY2U2YzkyNjJiNDViNjc2NzkzNGRkMGE5NWU2NzFmOWEwZmMyMDY4NScsCn0KSE9TVF9TVEFURSA9ICgKICAgICcuY29uZmlnL3Y3OS13b3JrZm9yY2UvZ29vZ2xlJywKICAgICcubG9jYWwvc2hhcmUvdjc5LXdvcmtmb3JjZS1vcGVyYXRpb25zJywKICAgICcubG9jYWwvc2hhcmUvdjc5LWFwcHJvdmVkLXRhc2std29ya2VyJywKKQpTVEFHRSA9ICdTVEFSVCcKCmRlZiBzdGFnZShuYW1lKToKICAgIGdsb2JhbCBTVEFHRQogICAgU1RBR0UgPSBuYW1lCgpjbGFzcyBIYWx0KEV4Y2VwdGlvbik6CiAgICBwYXNzCgpkZWYgbmVlZChvaywgY29kZSk6CiAgICBpZiBub3Qgb2s6CiAgICAgICAgcmFpc2UgSGFsdChjb2RlKQoKZGVmIGNhbGwoYXJncywgZGF0YT1Ob25lLCB0aW1lb3V0PTQ1KToKICAgIHRyeToKICAgICAgICBwID0gc3VicHJvY2Vzcy5ydW4oYXJncywgaW5wdXQ9ZGF0YSwgc3Rkb3V0PXN1YnByb2Nlc3MuUElQRSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgc3RkZXJyPXN1YnByb2Nlc3MuREVWTlVMTCwgdGltZW91dD10aW1lb3V0KQogICAgZXhjZXB0IChPU0Vycm9yLCBzdWJwcm9jZXNzLlRpbWVvdXRFeHBpcmVkKToKICAgICAgICByYWlzZSBIYWx0KCdSRUFEX0NPTU1BTkRfVU5BVkFJTEFCTEUnKSBmcm9tIE5vbmUKICAgIG5lZWQocC5yZXR1cm5jb2RlID09IDAsICdSRUFEX0NPTU1BTkRfRkFJTEVEX05PX1NFQ1JFVF9PVVRQVVQnKQogICAgcmV0dXJuIHAuc3Rkb3V0CgpkZWYgamNhbGwoYXJncyk6CiAgICByZXR1cm4ganNvbi5sb2FkcyhjYWxsKGFyZ3MpKQoKZGVmIHZhbHVlcyhvKToKICAgIHJldHVybiBkaWN0KHguc3BsaXQoJz0nLCAxKSBmb3IgeCBpbiBvWydDb25maWcnXS5nZXQoJ0VudicsIFtdKSBpZiAnPScgaW4geCkKCmRlZiBsb2NhbF9kb2NrZXIoaG9zdCk6CiAgICBuZWVkKG5vdCBvcy5lbnZpcm9uLmdldCgnRE9DS0VSX0hPU1QnKSBhbmQgbm90IG9zLmVudmlyb24uZ2V0KCdET0NLRVJfQ09OVEVYVCcpLCAnRE9DS0VSX09WRVJSSURFJykKICAgIGN0eCA9IGpjYWxsKFsnZG9ja2VyJywgJ2NvbnRleHQnLCAnaW5zcGVjdCddKQogICAgbmVlZChsZW4oY3R4KSA9PSAxIGFuZCBjdHhbMF1bJ0VuZHBvaW50cyddWydkb2NrZXInXVsnSG9zdCddIGluCiAgICAgICAgICgndW5peDovLy92YXIvcnVuL2RvY2tlci5zb2NrJywgJ3VuaXg6Ly8vcnVuL2RvY2tlci5zb2NrJyksICdET0NLRVJfTk9UX0xPQ0FMJykKICAgIG5lZWQoY2FsbChbJ2RvY2tlcicsICdpbmZvJywgJy0tZm9ybWF0JywgJ3t7Lk5hbWV9fSddKS5kZWNvZGUoKS5zdHJpcCgpID09IGhvc3QsICdET0NLRVJfREFFTU9OX0hPU1RfTUlTTUFUQ0gnKQoKZGVmIG1lbW9yeV9hdmFpbGFibGUoKToKICAgIGZvciBsaW5lIGluIFBhdGgoJy9wcm9jL21lbWluZm8nKS5yZWFkX3RleHQoKS5zcGxpdGxpbmVzKCk6CiAgICAgICAgaWYgbGluZS5zdGFydHN3aXRoKCdNZW1BdmFpbGFibGU6Jyk6CiAgICAgICAgICAgIHJldHVybiBpbnQobGluZS5zcGxpdCgpWzFdKSAqIDEwMjQKICAgIHJldHVybiAwCgpkZWYgb3ZlcmxhcChhLCBiKToKICAgIHJldHVybiBvcy5wYXRoLmNvbW1vbnBhdGgoW2EsIGJdKSBpbiAoYSwgYikKCmRlZiBwcml2YXRlX21ldGFkYXRhKHBhdGgpOgogICAgdHJ5OgogICAgICAgIHMgPSBwYXRoLmxzdGF0KCkKICAgICAgICByZXR1cm4geydwcmVzZW50JzogVHJ1ZSwgJ3JlZ3VsYXInOiBzdGF0LlNfSVNSRUcocy5zdF9tb2RlKSwKICAgICAgICAgICAgICAgICdkaXJlY3RvcnknOiBzdGF0LlNfSVNESVIocy5zdF9tb2RlKSwgJ293bmVkJzogcy5zdF91aWQgPT0gb3MuZ2V0dWlkKCksCiAgICAgICAgICAgICAgICAncHJpdmF0ZSc6IG5vdCAoc3RhdC5TX0lNT0RFKHMuc3RfbW9kZSkgJiAwbzA3Nyl9CiAgICBleGNlcHQgRmlsZU5vdEZvdW5kRXJyb3I6CiAgICAgICAgcmV0dXJuIHsncHJlc2VudCc6IEZhbHNlfQoKCkVYUEVDVEVEX0hVQl9TT1VSQ0VTID0gewogJy9ob21lL2ZpcmVsaW9uLy52NzktaGFyZGVuZWQtcGFpci1yZWxlYXNlcy9wYWlyLTIwMjYxMDI2VDAwMzYwN1otNmU2MDA2NzkxZjM0L21hbmlmZXN0LXY3OS1odWItY2FuZGlkYXRlLmpzb24nOiAnZTc4NTI3N2EzOTcwNDc2YzIxNGZhZGU5Mjc2M2ZhYzdhNDFhOTE1MWVjZTczNjVjNjdjOGNiMmI0MzkwMjNjNicKfQpFWFBFQ1RFRF9USVFVRVRfU09VUkNFUyA9IHsKICcvaG9tZS9maXJlbGlvbi8udjc5LWhhcmRlbmVkLXBhaXItcmVsZWFzZXMvcGFpci0yMDI2MTAyNlQwMDM2MDdaLTZlNjAwNjc5MWYzNC9tYW5pZmVzdC12NzktdGlxdWV0LW1hbmFnZXItY2FuZGlkYXRlLmpzb24nOiAnZThmMjFkMmM3OTdjNWY4ZWRmMDEyYmE0N2Q5MTIyYjhlZDE0MmI3MjU2MjgyMjA0OTI1ZWMwNzFjMTljOTAxMCcKfQpFWFBFQ1RFRF9JRFMgPSB7CiAndjc5LWh1Yic6ICdlMDJhM2I0YjQwYzUyMTI1NzU4MmMxNDU2YWNiNWY5ZjM5NDlkZDIyZDliMTE0NWRlM2MyYWVjNzdkM2FiYTVjJywKICd2NzktdGlxdWV0LW1hbmFnZXInOiAnMmFiNTE1NGY4MDA3MzNlNGUwOTBhYjQwZjRkMTZmMGM2YjA1NDk4NmZkMDEzYjc0ODNiOGIxZDI5MzdjZTk4MicsCiAndjc5LWJ1c2luZXNzLWFnZW50JzogJ2I3ZTU1OWMxY2RkNmNhNzNhZDQ2MjVjOTRjZTM5MzM0NTU4ZjNhZTg5MWRkNGJjN2FjY2ZkOWVkN2E0NzhkMjgnLAogJ3Y3OS1odWItcG9zdGdyZXMnOiAnNWI5N2I4MDRlZDk1OTBhMGZkNTRlODZmNGE2MTBhYWU1MjAwMTMxZjk1NjU0OTE4OWIwZTRhZWVhYjFlYzc1YycsCiAndGlxdWV0LXBvc3RncmVzJzogJzhlNGQxMDkzZmFmNzEwZjU1NTc5NWE3MGNhZjU3YjY3ZGE4ZGM3MWIyOTU1NWVlMGQ2ODFjNWM0N2UzYjExNDAnCn0KRVhQRUNURURfTU9VTlRTPXsKICd2NzktaHViJzp7Jy9hcHAvZGF0YSc6KCdiaW5kJyxUcnVlKSwnL3J1bi92Nzktd29ya2ZvcmNlLXJlcG9ydHMnOignYmluZCcsRmFsc2UpLCcvcnVuL3NlY3JldHMvdjc5LWFnZW50LXRva2VuJzooJ2JpbmQnLEZhbHNlKSwnL3J1bi9zZWNyZXRzL3Y3OS1jb28tZ2l0aHViLXRva2VuJzooJ2JpbmQnLEZhbHNlKSwnL3J1bi9zZWNyZXRzL3Y3OS1yZWFkb25seS1wbGF0Zm9ybS10b2tlbic6KCdiaW5kJyxGYWxzZSksJy9ydW4vc2VjcmV0cy92Nzktd29ya2ZvcmNlLXRva2VuJzooJ2JpbmQnLEZhbHNlKSwnL3J1bi92NzktZ29vZ2xlJzooJ3ZvbHVtZScsRmFsc2UpfSwKICd2NzktdGlxdWV0LW1hbmFnZXInOnsnL2FwcC9kYXRhJzooJ3ZvbHVtZScsVHJ1ZSksJy9hcHAvdXBsb2Fkcyc6KCd2b2x1bWUnLFRydWUpfSwKICd2NzktYnVzaW5lc3MtYWdlbnQnOnsnL3J1bi9zZWNyZXRzL3Y3OS1hZ2VudC10b2tlbic6KCdiaW5kJyxGYWxzZSl9LAp9ClBSSUNJTkdfUFJPQkU9ciIiIgppbXBvcnQgZnMgZnJvbSAnbm9kZTpmcyc7aW1wb3J0IHBhdGggZnJvbSAnbm9kZTpwYXRoJztpbXBvcnQgY3J5cHRvIGZyb20gJ25vZGU6Y3J5cHRvJzsKaW1wb3J0IHtjcmVhdGVQcmljaW5nUmVxdWVzdFN0b3JlfSBmcm9tICcuL3NlcnZlci9wcmljaW5nLXJlcXVlc3Qtc3RvcmUubWpzJzsKaW1wb3J0IHtnZXRXaXBheUNvbmZpZ30gZnJvbSAnLi9zZXJ2ZXIvd2lwYXktcHJvdmlkZXIubWpzJzsKdHJ5ewpjb25zdCByYXc9ZnMucmVhZEZpbGVTeW5jKCcvYXBwL3NlcnZlci50cycpO2lmKGNyeXB0by5jcmVhdGVIYXNoKCdzaGExJykudXBkYXRlKEJ1ZmZlci5mcm9tKCdibG9iICcrcmF3Lmxlbmd0aCsnXDAnKSkudXBkYXRlKHJhdykuZGlnZXN0KCdoZXgnKSE9PSc2Nzg0ZGVmOWEzOGQwMThmODdhYTg1ZTBkNzNlYzEwZDY1OTcyZGFmJylwcm9jZXNzLmV4aXQoMik7CmNvbnN0IGZpbGU9cGF0aC5yZXNvbHZlKHByb2Nlc3MuZW52LkRBVEFfRElSfHwnL2FwcC9kYXRhJywncHJpY2luZy1yZXF1ZXN0cy12MS5qc29uJyk7Y29uc3Qgc3Q9ZnMubHN0YXRTeW5jKGZpbGUpOwppZighc3QuaXNGaWxlKCl8fChzdC5tb2RlJjBvMDc3KXx8ZnMuZXhpc3RzU3luYyhmaWxlKycubG9jaycpfHxnZXRXaXBheUNvbmZpZygpLmVudmlyb25tZW50IT09J3NhbmRib3gnKXByb2Nlc3MuZXhpdCgzKTsKY29uc3Qgc2VjcmV0PVN0cmluZyhwcm9jZXNzLmVudi5WNzlfSFVCX1NFQ1VSSVRZX0tFWXx8cHJvY2Vzcy5lbnYuVjc5X1BMQVRGT1JNX1NIQVJFRF9TRUNSRVR8fCcnKS50cmltKCk7CmNvbnN0IHN0YXRlPWF3YWl0IGNyZWF0ZVByaWNpbmdSZXF1ZXN0U3RvcmUoe2ZpbGUsc2VjcmV0fSkucmVhZCgpOwpjb25zb2xlLmxvZyhKU09OLnN0cmluZ2lmeSh7cHJlc2VudDp0cnVlLHByaXZhdGU6dHJ1ZSxzaWduYXR1cmVWZXJpZmllZDp0cnVlLHJlcXVlc3RzOnN0YXRlLnJlcXVlc3RzLmxlbmd0aCxldmVudHM6c3RhdGUuZXZlbnRzLmxlbmd0aCx3aXBheVNhbmRib3g6dHJ1ZSxzb3VyY2VQaW5uZWQ6dHJ1ZX0pKTsKfWNhdGNoe3Byb2Nlc3MuZXhpdCg0KX0KIiIiCmRlZiB2YWxpZGF0ZV9maW5hbF9zY29wZShyZXBvcnQsc2VsZWN0ZWQpOgogZm9yIGFwcCxleHBlY3RlZCBpbiBFWFBFQ1RFRF9NT1VOVFMuaXRlbXMoKToKICByb3c9c2VsZWN0ZWRbYXBwXTthY3R1YWw9e21bJ0Rlc3RpbmF0aW9uJ106KG1bJ1R5cGUnXSxtWydSVyddKSBmb3IgbSBpbiByb3dbJ01vdW50cyddfQogIG5lZWQoYWN0dWFsPT1leHBlY3RlZCwnRklOQUxfQVBQTElDQVRJT05fTU9VTlRfU0NPUEVfRElGRkVSUycpCiAgaWYgYXBwPT0ndjc5LWh1Yic6CiAgIHBhdGhzPXJvd1snQ29uZmlnJ11bJ0xhYmVscyddWydjb20uZG9ja2VyLmNvbXBvc2UucHJvamVjdC5jb25maWdfZmlsZXMnXS5zcGxpdCgnLCcpCiAgIG5lZWQobGVuKHBhdGhzKT09MSBhbmQgc2V0KHBhdGhzKT09c2V0KEVYUEVDVEVEX0hVQl9TT1VSQ0VTKSwnRklOQUxfSFVCX0NPTVBPU0VfQ0hBSU5fRElGRkVSUycpCiAgIG5lZWQoYWxsKHJlcG9ydFsnY29tcG9zZV9pbnB1dF9oYXNoZXMnXS5nZXQocCk9PWRpZ2VzdCBmb3IgcCxkaWdlc3QgaW4gRVhQRUNURURfSFVCX1NPVVJDRVMuaXRlbXMoKSksJ0ZJTkFMX0hVQl9DT01QT1NFX0hBU0hfRElGRkVSUycpCiAgZWxpZiBhcHA9PSd2NzktdGlxdWV0LW1hbmFnZXInOgogICBwYXRocz1yb3dbJ0NvbmZpZyddWydMYWJlbHMnXVsnY29tLmRvY2tlci5jb21wb3NlLnByb2plY3QuY29uZmlnX2ZpbGVzJ10uc3BsaXQoJywnKQogICBuZWVkKGxlbihwYXRocyk9PTEgYW5kIHNldChwYXRocyk9PXNldChFWFBFQ1RFRF9USVFVRVRfU09VUkNFUyksJ0ZJTkFMX1RJUVVFVF9DT01QT1NFX0NIQUlOX0RJRkZFUlMnKQogICBuZWVkKGFsbChyZXBvcnRbJ2NvbXBvc2VfaW5wdXRfaGFzaGVzJ10uZ2V0KHApPT1kaWdlc3QgZm9yIHAsZGlnZXN0IGluIEVYUEVDVEVEX1RJUVVFVF9TT1VSQ0VTLml0ZW1zKCkpLCdGSU5BTF9USVFVRVRfQ09NUE9TRV9IQVNIX0RJRkZFUlMnKQogIGlmIGFwcD09J3Y3OS1odWInOgogICBnb29nbGU9bmV4dChtIGZvciBtIGluIHJvd1snTW91bnRzJ10gaWYgbVsnRGVzdGluYXRpb24nXT09Jy9ydW4vdjc5LWdvb2dsZScpCiAgIG5lZWQoZ29vZ2xlLmdldCgnTmFtZScpPT0ndjc5LWdvb2dsZS1jcmVkZW50aWFscy00OWY4MTM3NzY3NWEnLCdHT09HTEVfQ1JFREVOVElBTF9WT0xVTUVfRElGRkVSUycpCiBtZXRhZGF0YT1qc29uLmxvYWRzKGNhbGwoWydkb2NrZXInLCdleGVjJywndjc5LWh1YicsJ25vZGUnLCctLWlucHV0LXR5cGU9bW9kdWxlJywnLWUnLFBSSUNJTkdfUFJPQkVdKSkKIG5lZWQoYWxsKG1ldGFkYXRhLmdldChrKSBpcyBUcnVlIGZvciBrIGluICgncHJlc2VudCcsJ3ByaXZhdGUnLCdzaWduYXR1cmVWZXJpZmllZCcsJ3dpcGF5U2FuZGJveCcsJ3NvdXJjZVBpbm5lZCcpKSwnUFJJQ0lOR19MRURHRVJfT1JfU0FOREJPWF9DSEVDS19GQUlMRUQnKQogbmVlZChpc2luc3RhbmNlKG1ldGFkYXRhLmdldCgncmVxdWVzdHMnKSxpbnQpIGFuZCBtZXRhZGF0YVsncmVxdWVzdHMnXT49MSwnQUNDRVBURURfUFJJQ0lOR19SRVFVRVNUX05PVF9GT1VORCcpCiByZXBvcnRbJ3ByaWNpbmdfbGVkZ2VyX21ldGFkYXRhJ109bWV0YWRhdGEKIHJlcG9ydFsnbW91bnRfY291bnQnXT1zdW0obGVuKHYpIGZvciB2IGluIEVYUEVDVEVEX01PVU5UUy52YWx1ZXMoKSkKIHJlcG9ydFsnZXhwZWN0ZWRfZW5jcnlwdGVkX2FydGlmYWN0cyddPTUrcmVwb3J0Wydtb3VudF9jb3VudCddCiByZXBvcnRbJ2N1cnJlbnRfaHViX3NvdXJjZSddPSdjMTJlNTRiZGI1MmY4OTk2ZmFlMTk2ODhkNzQzNTRkNzMxZTdkZTI3JwogcmVwb3J0Wydtb3VudGVkX2dvb2dsZV9jcmVkZW50aWFsc19jb250ZW50c19yZWFkJ109RmFsc2UKIHJlcG9ydFsnZmluYWxfcmVjb3Zlcnlfc2NvcGUnXT0nRklWRV9DVVJSRU5UX0lNQUdFU19UV09fREFUQUJBU0VTX1RFTl9NT1VOVFNfUFJJVkFURV9IT1NUX1NUQVRFJwoKZGVmIHNlcnZlcigpOgogICAgc3RhZ2UoJ1NFUlZFUl9JREVOVElUWV9BTkRfRE9DS0VSJykKICAgIG5lZWQoc29ja2V0LmdldGhvc3RuYW1lKCkgPT0gJ3Y3OXNsJyBhbmQgb3MuZ2V0ZXVpZCgpICE9IDAgYW5kCiAgICAgICAgIFBhdGguaG9tZSgpID09IFBhdGgoJy9ob21lL2ZpcmVsaW9uJyksICdXUk9OR19TRVJWRVJfVVNFUicpCiAgICBsb2NhbF9kb2NrZXIoJ3Y3OXNsJykKICAgIG5hbWVzID0gY2FsbChbJ2RvY2tlcicsICdwcycsICctLWFsbCcsICctLWZvcm1hdCcsICd7ey5OYW1lc319J10pLmRlY29kZSgpLnNwbGl0bGluZXMoKQogICAgcm93cyA9IGpjYWxsKFsnZG9ja2VyJywgJ2luc3BlY3QnLCAqbmFtZXNdKQogICAgYWxsX3Jvd3MgPSB7clsnTmFtZSddLmxzdHJpcCgnLycpOiByIGZvciByIGluIHJvd3N9CiAgICBuZWVkKHNldChJTUFHRVMpIDw9IHNldChhbGxfcm93cyksICdSRVFVSVJFRF9DT05UQUlORVJfQUJTRU5UJykKICAgIHNlbGVjdGVkID0ge246IGFsbF9yb3dzW25dIGZvciBuIGluIElNQUdFU30KICAgIGJsb2NrZXJzLCBwaW5zLCBjb21wb3NlX2lucHV0cywgbW91bnRzID0gW10sIHt9LCB7fSwgW10KICAgIGltYWdlX2J5dGVzID0gMAogICAgZm9yIG5hbWUsIG8gaW4gc2VsZWN0ZWQuaXRlbXMoKToKICAgICAgICBzdGFnZSgnU0VSVkVSX0NPTlRBSU5FUl8nICsgbmFtZS5yZXBsYWNlKCctJywgJ18nKS51cHBlcigpKQogICAgICAgIGhlYWx0aHkgPSBvWydTdGF0ZSddLmdldCgnUnVubmluZycpIGFuZCBvWydTdGF0ZSddLmdldCgnSGVhbHRoJywge30pLmdldCgnU3RhdHVzJykgPT0gJ2hlYWx0aHknCiAgICAgICAgbmVlZChvWydJbWFnZSddID09IElNQUdFU1tuYW1lXSBhbmQgb1snSWQnXT09RVhQRUNURURfSURTW25hbWVdIGFuZCBoZWFsdGh5LCAnUElOTkVEX0lNQUdFX0lEX09SX0hFQUxUSF9DSEFOR0VEJykKICAgICAgICBwaW5zW25hbWVdID0geydpZCc6IG9bJ0lkJ10sICdpbWFnZSc6IG9bJ0ltYWdlJ10sICdoZWFsdGh5JzogVHJ1ZX0KICAgICAgICBpbWFnZV9ieXRlcyArPSBqY2FsbChbJ2RvY2tlcicsICdpbWFnZScsICdpbnNwZWN0Jywgb1snSW1hZ2UnXV0pWzBdWydTaXplJ10KICAgICAgICBsYWJlbHMgPSBvWydDb25maWcnXS5nZXQoJ0xhYmVscycpIG9yIHt9CiAgICAgICAgcGF0aHMgPSBsYWJlbHMuZ2V0KCdjb20uZG9ja2VyLmNvbXBvc2UucHJvamVjdC5jb25maWdfZmlsZXMnLCAnJykuc3BsaXQoJywnKQogICAgICAgIG5lZWQoYWxsKHAuc3RhcnRzd2l0aCgnLycpIGZvciBwIGluIHBhdGhzKSwgJ0NPTVBPU0VfQ0hBSU5fVU5BVkFJTEFCTEUnKQogICAgICAgIGZvciB0ZXh0IGluIHBhdGhzOgogICAgICAgICAgICBwID0gUGF0aCh0ZXh0KQogICAgICAgICAgICBzID0gcC5sc3RhdCgpCiAgICAgICAgICAgIG5lZWQoc3RhdC5TX0lTUkVHKHMuc3RfbW9kZSkgYW5kIHMuc3Rfc2l6ZSA8PSAyKjEwMjQqKjIgYW5kCiAgICAgICAgICAgICAgICAgcy5zdF91aWQgaW4gKDAsIG9zLmdldHVpZCgpKSBhbmQgbm90IHMuc3RfbW9kZSAmIDBvMDAyLCAnQ09NUE9TRV9JTlBVVF9VTlNBRkUnKQogICAgICAgICAgICBjb21wb3NlX2lucHV0c1t0ZXh0XSA9IGhhc2hsaWIuc2hhMjU2KHAucmVhZF9ieXRlcygpKS5oZXhkaWdlc3QoKQogICAgICAgIGlmIG5hbWUgaW4gQVBQUzoKICAgICAgICAgICAgZm9yIG0gaW4gby5nZXQoJ01vdW50cycsIFtdKToKICAgICAgICAgICAgICAgIG5lZWQobVsnVHlwZSddIGluICgnYmluZCcsICd2b2x1bWUnKSBhbmQgbS5nZXQoJ1NvdXJjZScsICcnKS5zdGFydHN3aXRoKCcvJyksICdNT1VOVF9UWVBFX1VOUkVWSUVXRUQnKQogICAgICAgICAgICAgICAgc291cmNlID0gbVsnU291cmNlJ10KICAgICAgICAgICAgICAgIHNoYXJlZCA9IFtdCiAgICAgICAgICAgICAgICBmb3Igb3RoZXIsIGZvcmVpZ24gaW4gYWxsX3Jvd3MuaXRlbXMoKToKICAgICAgICAgICAgICAgICAgICBpZiBvdGhlciBpbiBBUFBTIG9yIG5vdCBmb3JlaWduWydTdGF0ZSddLmdldCgnUnVubmluZycpOgogICAgICAgICAgICAgICAgICAgICAgICBjb250aW51ZQogICAgICAgICAgICAgICAgICAgIGZvciBmbSBpbiBmb3JlaWduLmdldCgnTW91bnRzJywgW10pOgogICAgICAgICAgICAgICAgICAgICAgICBpZiBmbS5nZXQoJ1JXJykgYW5kIGZtLmdldCgnU291cmNlJykgYW5kIG92ZXJsYXAoc291cmNlLCBmbVsnU291cmNlJ10pOgogICAgICAgICAgICAgICAgICAgICAgICAgICAgc2hhcmVkLmFwcGVuZChvdGhlcikKICAgICAgICAgICAgICAgIGlmIHNoYXJlZDoKICAgICAgICAgICAgICAgICAgICBibG9ja2Vycy5hcHBlbmQoJ1NIQVJFRF9XUklURVJfJyArIG5hbWUpCiAgICAgICAgICAgICAgICBtb3VudHMuYXBwZW5kKHsnY29udGFpbmVyJzogbmFtZSwgJ2Rlc3RpbmF0aW9uJzogbVsnRGVzdGluYXRpb24nXSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICd0eXBlJzogbVsnVHlwZSddLCAncncnOiBtWydSVyddLCAnb3RoZXJfd3JpdGVyX2NvdW50JzogbGVuKHNldChzaGFyZWQpKX0pCiAgICBoLCB0ID0gdmFsdWVzKHNlbGVjdGVkWyd2NzktaHViJ10pLCB2YWx1ZXMoc2VsZWN0ZWRbJ3Y3OS10aXF1ZXQtbWFuYWdlciddKQogICAgc3RhZ2UoJ1NFUlZFUl9TRUNVUklUWV9BTkRfUFJJQ0VfSU5QVVRTJykKICAgIG5lZWQoaC5nZXQoJ1Y3OV9SRVFVSVJFX0FETUlOX01GQScpID09ICcxJyBhbmQKICAgICAgICAgaC5nZXQoJ1Y3OV9IVUJfVElRVUVUX1NFU1NJT05fQklORElORycpID09ICcxJyBhbmQKICAgICAgICAgdC5nZXQoJ1Y3OV9USVFVRVRfU0VTU0lPTl9CSU5ESU5HX0VOQUJMRUQnKSA9PSAnMScgYW5kCiAgICAgICAgIHQuZ2V0KCdWNzlfQUxMT1dfTEVHQUNZX0FVVEgnKSA9PSAnMCcgYW5kCiAgICAgICAgIHQuZ2V0KCdWNzlfRU5USVRMRU1FTlRfUkVDSEVDS19FTkFCTEVEJykgPT0gJzEnLCAnU0VDVVJJVFlfRkxBR1NfQ0hBTkdFRCcpCiAgICBuZWVkKGguZ2V0KCdWNzlfVElRVUVUX0xBVU5DSF9TRUNSRVQnKSBhbmQKICAgICAgICAgaFsnVjc5X1RJUVVFVF9MQVVOQ0hfU0VDUkVUJ10gPT0gdC5nZXQoJ1Y3OV9USVFVRVRfTEFVTkNIX1NFQ1JFVCcpLCAnU1NPX1NFQ1JFVF9NSVNNQVRDSCcpCiAgICBwcmljZV9pbnB1dHNfcHJlc2VudCA9IGFsbCh0LmdldCgnUExBTl9QUklDRV8nICsgeCkgZm9yIHggaW4gKCdTVEFSVEVSJywnUFJPJywnRU5URVJQUklTRScpKQogICAgaWYgbm90IHByaWNlX2lucHV0c19wcmVzZW50OgogICAgICAgIGJsb2NrZXJzLmFwcGVuZCgnRlJPWkVOX1BSSUNFX0lOUFVUX0FCU0VOVCcpCiAgICBkYl92ZXJzaW9ucyA9IHt9CiAgICBmb3IgZGIsIG1ham9yIGluIFsoJ3Y3OS1odWItcG9zdGdyZXMnLCAnMTcnKSwgKCd0aXF1ZXQtcG9zdGdyZXMnLCAnMTYnKV06CiAgICAgICAgc3RhZ2UoJ1NFUlZFUl9EQVRBQkFTRV8nICsgbWFqb3IpCiAgICAgICAgdmVyc2lvbiA9IGNhbGwoWydkb2NrZXInLCdleGVjJyxkYiwncGdfZHVtcCcsJy0tdmVyc2lvbiddKS5kZWNvZGUoKQogICAgICAgIG5lZWQocmUuc2VhcmNoKHInUG9zdGdyZVNRTFwpICcrbWFqb3IrcidcLicsIHZlcnNpb24pLCAnUEdfRFVNUF9WRVJTSU9OX0NIQU5HRUQnKQogICAgICAgIGNhbGwoWydkb2NrZXInLCdleGVjJyxkYiwnc2gnLCctYycsCiAgICAgICAgICAgICAgJ3BnX2lzcmVhZHkgLXEgLVUgIiR7UE9TVEdSRVNfVVNFUjotcG9zdGdyZXN9IiAtZCAiJHtQT1NUR1JFU19EQjotJHtQT1NUR1JFU19VU0VSOi1wb3N0Z3Jlc319IiddKQogICAgICAgIGRiX3ZlcnNpb25zW2RiXSA9IHsnbWFqb3InOiBtYWpvciwgJ3JlYWR5JzogVHJ1ZX0KICAgIHRpbWVycyA9IFtdCiAgICBzdGFnZSgnU0VSVkVSX1RJTUVSU19BTkRfSE9TVF9TVEFURScpCiAgICBsaXN0aW5nID0gY2FsbChbJ3N5c3RlbWN0bCcsJy0tdXNlcicsJ2xpc3QtdW5pdHMnLCctLXR5cGU9dGltZXInLCctLXN0YXRlPWFjdGl2ZScsJy0tbm8tbGVnZW5kJywnLS1wbGFpbiddKS5kZWNvZGUoKQogICAgZm9yIGxpbmUgaW4gbGlzdGluZy5zcGxpdGxpbmVzKCk6CiAgICAgICAgdW5pdCA9IGxpbmUuc3BsaXQoKVswXQogICAgICAgIGlmIHJlLmZ1bGxtYXRjaChyJ3Y3OVstQS1aYS16MC05QF8uXStcLnRpbWVyJywgdW5pdCkgYW5kIHJlLnNlYXJjaChyJ3dvcmtmb3JjZXxyZWxlYXNlfHRhc2snLCB1bml0KToKICAgICAgICAgICAgdGltZXJzLmFwcGVuZCh1bml0KQogICAgaG9zdF9zdGF0ZSA9IHtwOiBwcml2YXRlX21ldGFkYXRhKFBhdGguaG9tZSgpL3ApIGZvciBwIGluIEhPU1RfU1RBVEV9CiAgICBmb3IgcCwgbWV0YSBpbiBob3N0X3N0YXRlLml0ZW1zKCk6CiAgICAgICAgaWYgbm90IG1ldGEuZ2V0KCdwcmVzZW50Jykgb3Igbm90IG1ldGEuZ2V0KCdkaXJlY3RvcnknKSBvciBub3QgbWV0YS5nZXQoJ293bmVkJyk6CiAgICAgICAgICAgIGJsb2NrZXJzLmFwcGVuZCgnSE9TVF9TVEFURV9VTlNBRkVfJyArIHAucnNwbGl0KCcvJywxKVstMV0pCiAgICBnb29nbGUgPSB7bjogcHJpdmF0ZV9tZXRhZGF0YShQYXRoLmhvbWUoKS9IT1NUX1NUQVRFWzBdL24pIGZvciBuIGluICgnY2xpZW50Lmpzb24nLCdjcmVkZW50aWFscy5qc29uJyl9CiAgICBpZiBub3QgYWxsKG0uZ2V0KCdyZWd1bGFyJykgYW5kIG0uZ2V0KCdvd25lZCcpIGFuZCBtLmdldCgncHJpdmF0ZScpIGZvciBtIGluIGdvb2dsZS52YWx1ZXMoKSk6CiAgICAgICAgYmxvY2tlcnMuYXBwZW5kKCdHT09HTEVfQ1JFREVOVElBTF9GSUxFX1VOU0FGRScpCiAgICAjIEluc3BlY3QgbWV0YWRhdGEgb25seTsgZG8gbm90IHJlYWQgY3JlZGVudGlhbHMgb3IgcXVldWUgcGF5bG9hZHMuCiAgICB3b3JrZm9yY2VfdW5pdHMgPSBbXQogICAgdW5pdF9yb290ID0gUGF0aC5ob21lKCkvJy5jb25maWcvc3lzdGVtZC91c2VyJwogICAgaWYgdW5pdF9yb290LmlzX2RpcigpOgogICAgICAgIHdvcmtmb3JjZV91bml0cyA9IHNvcnRlZChwLm5hbWUgZm9yIHAgaW4gdW5pdF9yb290Lml0ZXJkaXIoKQogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGlmIHAuaXNfZmlsZSgpIGFuZCByZS5mdWxsbWF0Y2gocid2NzlbLUEtWmEtejAtOUBfLl0rXC4oc2VydmljZXx0aW1lciknLHAubmFtZSkKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBhbmQgcmUuc2VhcmNoKHInd29ya2ZvcmNlfHJlbGVhc2V8dGFzaycscC5uYW1lKSkKICAgIGxvY2sgPSBQYXRoLmhvbWUoKS8nLnY3OS1wb3J0Zm9saW8tcm9sbG91dC5sb2NrJwogICAgaWYgbG9jay5leGlzdHMoKToKICAgICAgICBuZWVkKG5vdCBsb2NrLmlzX3N5bWxpbmsoKSBhbmQgbG9jay5pc19maWxlKCksICdPUEVSQVRJT05fTE9DS19VTlNBRkUnKQogICAgICAgIHdpdGggbG9jay5vcGVuKCdyYicpIGFzIGY6CiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIGZjbnRsLmZsb2NrKGYsIGZjbnRsLkxPQ0tfRVggfCBmY250bC5MT0NLX05CKQogICAgICAgICAgICAgICAgZmNudGwuZmxvY2soZiwgZmNudGwuTE9DS19VTikKICAgICAgICAgICAgZXhjZXB0IEJsb2NraW5nSU9FcnJvcjoKICAgICAgICAgICAgICAgIGJsb2NrZXJzLmFwcGVuZCgnT1RIRVJfUkVMRUFTRV9PUEVSQVRJT05fUlVOTklORycpCiAgICBmb3IgbiBpbiBzZWxlY3RlZDoKICAgICAgICBjdXJyZW50ID0gamNhbGwoWydkb2NrZXInLCdpbnNwZWN0JyxuXSlbMF0KICAgICAgICBuZWVkKGN1cnJlbnRbJ0lkJ10gPT0gc2VsZWN0ZWRbbl1bJ0lkJ10gYW5kIGN1cnJlbnRbJ0ltYWdlJ10gPT0gc2VsZWN0ZWRbbl1bJ0ltYWdlJ10sICdSVU5USU1FX0NIQU5HRURfRFVSSU5HX1BSRUZMSUdIVCcpCiAgICByZXN1bHQgPSB7J21vZGUnOiAnUkVBRF9PTkxZX0NIRUNLUE9JTlRfUkVBRElORVNTJywgJ2NoZWNrZWRfYXQnOiBkYXRldGltZS5kYXRldGltZS5ub3coZGF0ZXRpbWUudGltZXpvbmUudXRjKS5pc29mb3JtYXQoKSwKICAgICAgICAgICAgICAncGlucyc6IHBpbnMsICdjb21wb3NlX2lucHV0X2hhc2hlcyc6IGNvbXBvc2VfaW5wdXRzLCAnYXBwX21vdW50cyc6IG1vdW50cywKICAgICAgICAgICAgICAnaW1hZ2VfYnl0ZXMnOiBpbWFnZV9ieXRlcywgJ3NlcnZlcl9mcmVlX2J5dGVzJzogc2h1dGlsLmRpc2tfdXNhZ2UoUGF0aC5ob21lKCkpLmZyZWUsCiAgICAgICAgICAgICAgJ3NlcnZlcl9hdmFpbGFibGVfbWVtb3J5X2J5dGVzJzogbWVtb3J5X2F2YWlsYWJsZSgpLCAnZGF0YWJhc2VzJzogZGJfdmVyc2lvbnMsCiAgICAgICAgICAgICAgJ2FjdGl2ZV90aW1lcnNfdG9fcXVpZXNjZSc6IHNvcnRlZCh0aW1lcnMpLCAnd29ya2ZvcmNlX3VuaXRfZmlsZXMnOiB3b3JrZm9yY2VfdW5pdHMsCiAgICAgICAgICAgICAgJ2hvc3Rfc3RhdGVfbWV0YWRhdGEnOiBob3N0X3N0YXRlLCAnZ29vZ2xlX2ZpbGVfbWV0YWRhdGEnOiBnb29nbGUsCiAgICAgICAgICAgICAgJ2Zyb3plbl9wcmljZV9pbnB1dHNfYXZhaWxhYmxlX25vdF9wcmludGVkJzogYm9vbChwcmljZV9pbnB1dHNfcHJlc2VudCksCiAgICAgICAgICAgICAgJ2dvb2dsZV9jb250ZW50c19yZWFkJzogRmFsc2UsICdwcm9kdWN0aW9uX2NoYW5nZWQnOiBGYWxzZSwKICAgICAgICAgICAgICAnYmxvY2tlcnMnOiBzb3J0ZWQoc2V0KGJsb2NrZXJzKSksICdjYXB0dXJlX3BlcmZvcm1lZCc6IEZhbHNlLCAncmVzdG9yZV9wZXJmb3JtZWQnOiBGYWxzZX0KICAgIHZhbGlkYXRlX2ZpbmFsX3Njb3BlKHJlc3VsdCxzZWxlY3RlZCkKICAgIHJlc3VsdFsnaW52ZW50b3J5X3NoYTI1NiddID0gaGFzaGxpYi5zaGEyNTYoanNvbi5kdW1wcygKICAgICAgICB7J3BpbnMnOiBwaW5zLCAnaW5wdXRzJzogY29tcG9zZV9pbnB1dHMsICd0aW1lcnMnOiBzb3J0ZWQodGltZXJzKSwgJ21vdW50cyc6IG1vdW50cywgJ2ZpbmFsX3Njb3BlJzpyZXN1bHRbJ2ZpbmFsX3JlY292ZXJ5X3Njb3BlJ119LAogICAgICAgIHNvcnRfa2V5cz1UcnVlKS5lbmNvZGUoKSkuaGV4ZGlnZXN0KCkKICAgIHJldHVybiByZXN1bHQKCmRlZiBhY2VyKCk6CiAgICBzdGFnZSgnQUNFUl9JREVOVElUWV9BTkRfRE9DS0VSJykKICAgIG5lZWQoc29ja2V0LmdldGhvc3RuYW1lKCkgPT0gJ2ZpcmVsaW9uLUFzcGlyZS1BMzE1LTUxJyBhbmQgb3MuZ2V0ZXVpZCgpICE9IDAsICdSVU5fT05fTk9OUk9PVF9BQ0VSJykKICAgIGxvY2FsX2RvY2tlcihzb2NrZXQuZ2V0aG9zdG5hbWUoKSkKICAgIHN0YWdlKCdBQ0VSX1JFQ09WRVJZX0tFWV9NRVRBREFUQScpCiAgICBmaW5nZXJwcmludHMgPSBjYWxsKFsnZ3BnJywnLS1iYXRjaCcsJy0td2l0aC1jb2xvbnMnLCctLWZpbmdlcnByaW50JyxSRUNJUElFTlRdKS5kZWNvZGUoKQogICAgbmVlZCgnZnByOjo6Ojo6Ojo6JytSRUNJUElFTlQrJzonIGluIGZpbmdlcnByaW50cywgJ1JFQ09WRVJZX1BVQkxJQ19LRVlfVU5BVkFJTEFCTEUnKQogICAga2V5cyA9IGNhbGwoWydncGcnLCctLWJhdGNoJywnLS13aXRoLWNvbG9ucycsJy0tbGlzdC1zZWNyZXQta2V5cycsUkVDSVBJRU5UXSkuZGVjb2RlKCkKICAgIG5lZWQoYW55KGxpbmUuc3RhcnRzd2l0aCgnc2VjOicpIG9yIGxpbmUuc3RhcnRzd2l0aCgnc2VjIzonKSBmb3IgbGluZSBpbiBrZXlzLnNwbGl0bGluZXMoKSksICdSRUNPVkVSWV9QUklWQVRFX0tFWV9VTkFWQUlMQUJMRScpCiAgICBwcmludCgnQUNFUl9SRUNPVkVSWV9LRVk9UElOTkVEX1BVQkxJQ19BTkRfUFJJVkFURV9QUkVTRU5UJywgZmx1c2g9VHJ1ZSkKICAgIHByaW50KCdBQ0VSX0ZSRUVfQllURVM9JytzdHIoc2h1dGlsLmRpc2tfdXNhZ2UoUGF0aC5ob21lKCkpLmZyZWUpLCBmbHVzaD1UcnVlKQogICAgcHJpbnQoJ0FDRVJfQVZBSUxBQkxFX01FTU9SWV9CWVRFUz0nK3N0cihtZW1vcnlfYXZhaWxhYmxlKCkpLCBmbHVzaD1UcnVlKQogICAgY29tbWFuZCA9IFsnc3NoJywnLVQnLCctbycsJ0JhdGNoTW9kZT15ZXMnLCctbycsJ1N0cmljdEhvc3RLZXlDaGVja2luZz15ZXMnLAogICAgICAgICAgICAgICAnLW8nLCdDb25uZWN0VGltZW91dD0xMCcsJ2ZpcmVsaW9uQHY3OXNsJywncHl0aG9uMyAtQiAtIC0tc2VydmVyJ10KICAgIHN0YWdlKCdTRVJWRVJfUkVBRF9PTkxZX0lOVkVOVE9SWScpCiAgICB0cnk6CiAgICAgICAgcHJvY2VzcyA9IHN1YnByb2Nlc3MucnVuKGNvbW1hbmQsIGlucHV0PVBhdGgoX19maWxlX18pLnJlYWRfYnl0ZXMoKSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgc3Rkb3V0PXN1YnByb2Nlc3MuUElQRSwgc3RkZXJyPXN1YnByb2Nlc3MuREVWTlVMTCwgdGltZW91dD0xODApCiAgICBleGNlcHQgKE9TRXJyb3IsIHN1YnByb2Nlc3MuVGltZW91dEV4cGlyZWQpOgogICAgICAgIHJhaXNlIEhhbHQoJ1NTSF9SRUFEX1VOQVZBSUxBQkxFJykgZnJvbSBOb25lCiAgICByYXcgPSBwcm9jZXNzLnN0ZG91dAogICAgaWYgcHJvY2Vzcy5yZXR1cm5jb2RlOgogICAgICAgIHRyeToKICAgICAgICAgICAgZXJyb3IgPSBqc29uLmxvYWRzKHJhdykKICAgICAgICAgICAgZm9yIGtleSBpbiAoJ2Vycm9yX3N0YWdlJywgJ2Vycm9yJyk6CiAgICAgICAgICAgICAgICBpZiByZS5mdWxsbWF0Y2gocidbQS1aMC05X10rJywgc3RyKGVycm9yLmdldChrZXksICcnKSkpOgogICAgICAgICAgICAgICAgICAgIHByaW50KCdTRVJWRVJfJyArIGtleS51cHBlcigpICsgJz0nICsgZXJyb3Jba2V5XSwgZmx1c2g9VHJ1ZSkKICAgICAgICBleGNlcHQgKFZhbHVlRXJyb3IsIFR5cGVFcnJvcik6CiAgICAgICAgICAgIHBhc3MKICAgICAgICByYWlzZSBIYWx0KCdTRVJWRVJfUkVBRElORVNTX0ZBSUxFRCcpCiAgICByZXBvcnQgPSBqc29uLmxvYWRzKHJhdykKICAgIG5lZWQocmVwb3J0LmdldCgnbW9kZScpID09ICdSRUFEX09OTFlfQ0hFQ0tQT0lOVF9SRUFESU5FU1MnLCAnUkVNT1RFX1JFUE9SVF9JTlZBTElEJykKICAgIHByaW50KGpzb24uZHVtcHMocmVwb3J0LCBpbmRlbnQ9Miwgc29ydF9rZXlzPVRydWUpLCBmbHVzaD1UcnVlKQogICAgbWluaW11bSA9IG1heCgyMCoxMDI0KiozLCAyKnJlcG9ydFsnaW1hZ2VfYnl0ZXMnXSsxMCoxMDI0KiozKQogICAgZW5vdWdoID0gc2h1dGlsLmRpc2tfdXNhZ2UoUGF0aC5ob21lKCkpLmZyZWUgPj0gbWluaW11bSBhbmQgcmVwb3J0WydzZXJ2ZXJfZnJlZV9ieXRlcyddID49IG1pbmltdW0KICAgIHByaW50KCdDSEVDS1BPSU5UX0RJU0tfSEVBRFJPT009JysoJ1BBU1MnIGlmIGVub3VnaCBlbHNlICdJTlNVRkZJQ0lFTlQnKSwgZmx1c2g9VHJ1ZSkKICAgIHByaW50KCdORVhUPVBJTl9GSU5BTF9FTkNSWVBURURfQ0FQVFVSRV9BTkRfSVNPTEFURURfUkVTVE9SRScsIGZsdXNoPVRydWUpCiAgICBwcmludCgnQ0FQVFVSRV9BTkRfUkVTVE9SRT1OT1RfUlVOJywgZmx1c2g9VHJ1ZSkKCmRlZiBzZWxmX3Rlc3QoKToKICAgIGFzc2VydCBvdmVybGFwKCcvYS9iJywnL2EvYi9jJykgYW5kIG5vdCBvdmVybGFwKCcvYS9iJywnL2EvYmMnKQogICAgYXNzZXJ0IGxlbihJTUFHRVMpID09IDUgYW5kIGxlbihBUFBTKSA9PSAzIGFuZCBsZW4oRVhQRUNURURfSURTKT09NQogICAgYXNzZXJ0IGFsbChyZS5mdWxsbWF0Y2gocidzaGEyNTY6W2EtZjAtOV17NjR9JywgeCkgZm9yIHggaW4gSU1BR0VTLnZhbHVlcygpKQogICAgYXNzZXJ0IGxlbihSRUNJUElFTlQpID09IDQwCiAgICBhc3NlcnQgbm90IHByaXZhdGVfbWV0YWRhdGEoUGF0aCgnL25vbmV4aXN0ZW50LXY3OS10ZXN0LXBhdGgnKSkuZ2V0KCdwcmVzZW50JykKICAgIGltcG9ydCB0ZW1wZmlsZQogICAgd2l0aCB0ZW1wZmlsZS5UZW1wb3JhcnlEaXJlY3RvcnkoKSBhcyB0bXA6CiAgICAgICAgcD1QYXRoKHRtcCkvJ3Rlc3QnOyBwLndyaXRlX3RleHQoJ2ZpeHR1cmUnKTsgcC5jaG1vZCgwbzYwMCkKICAgICAgICBhc3NlcnQgcHJpdmF0ZV9tZXRhZGF0YShwKVsncmVndWxhciddIGFuZCBwcml2YXRlX21ldGFkYXRhKHApWydwcml2YXRlJ10KICAgICAgICBwLmNobW9kKDBvNjQ0KTsgYXNzZXJ0IG5vdCBwcml2YXRlX21ldGFkYXRhKHApWydwcml2YXRlJ10KICAgICAgICBsaW5rPVBhdGgodG1wKS8nbGluayc7IGxpbmsuc3ltbGlua190byhwKTsgYXNzZXJ0IG5vdCBwcml2YXRlX21ldGFkYXRhKGxpbmspWydyZWd1bGFyJ10KICAgIHByaW50KCdTRUxGX1RFU1Q9UEFTU19TQ09QRV9QSU5TX09WRVJMQVBfQU5EX1BSSVZBVEVfTUVUQURBVEEnKQoKaWYgX19uYW1lX18gPT0gJ19fbWFpbl9fJzoKICAgIHBhcnNlcj1hcmdwYXJzZS5Bcmd1bWVudFBhcnNlcihkZXNjcmlwdGlvbj1fX2RvY19fKQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLS1zZXJ2ZXInLCBhY3Rpb249J3N0b3JlX3RydWUnKQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLS1zZWxmLXRlc3QnLCBhY3Rpb249J3N0b3JlX3RydWUnKQogICAgYXJncz1wYXJzZXIucGFyc2VfYXJncygpCiAgICB0cnk6CiAgICAgICAgaWYgYXJncy5zZWxmX3Rlc3Q6CiAgICAgICAgICAgIHNlbGZfdGVzdCgpCiAgICAgICAgZWxpZiBhcmdzLnNlcnZlcjoKICAgICAgICAgICAgcHJpbnQoanNvbi5kdW1wcyhzZXJ2ZXIoKSwgc29ydF9rZXlzPVRydWUpKQogICAgICAgIGVsc2U6CiAgICAgICAgICAgIGFjZXIoKQogICAgZXhjZXB0IChIYWx0LCBPU0Vycm9yLCBWYWx1ZUVycm9yLCBLZXlFcnJvciwgVHlwZUVycm9yKSBhcyBlcnJvcjoKICAgICAgICByZWFzb24gPSBzdHIoZXJyb3IpIGlmIGlzaW5zdGFuY2UoZXJyb3IsIEhhbHQpIGFuZCByZS5mdWxsbWF0Y2gocidbQS1aMC05X10rJywgc3RyKGVycm9yKSkgZWxzZSAnUkVBRElORVNTX01FVEFEQVRBX1VOQVZBSUxBQkxFJwogICAgICAgIGlmIGFyZ3Muc2VydmVyOgogICAgICAgICAgICBwcmludChqc29uLmR1bXBzKHsnZXJyb3Jfc3RhZ2UnOiBTVEFHRSwgJ2Vycm9yJzogcmVhc29ufSksIGZsdXNoPVRydWUpCiAgICAgICAgZWxzZToKICAgICAgICAgICAgcHJpbnQoJ0ZBSUxFRF9TVEFHRT0nICsgU1RBR0UsIGZsdXNoPVRydWUpCiAgICAgICAgICAgIHByaW50KCdTVE9QPScgKyByZWFzb24sIGZsdXNoPVRydWUpCiAgICAgICAgc3lzLmV4aXQoMSkK'
INVENTORY = None  # Bind fresh exact V8 runtime attestation before capture.
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
    launch=shlex.join(['python3','-B','-u',directory+'/runner.py','--server-capture',directory])
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
    a=p.parse_args()
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
