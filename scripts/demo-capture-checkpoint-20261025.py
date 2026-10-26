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

READINESS_B64='IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJSZWFkLW9ubHkgY2hlY2twb2ludCByZWFkaW5lc3MuIE5ldmVyIHBhdXNlcywgY2FwdHVyZXMgb3IgcmVzdG9yZXMgcHJvZHVjdGlvbi4iIiIKaW1wb3J0IGFyZ3BhcnNlCmltcG9ydCBkYXRldGltZQppbXBvcnQgZmNudGwKaW1wb3J0IGhhc2hsaWIKaW1wb3J0IGpzb24KaW1wb3J0IG9zCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBvcnQgcmUKaW1wb3J0IHNodXRpbAppbXBvcnQgc29ja2V0CmltcG9ydCBzdGF0CmltcG9ydCBzdWJwcm9jZXNzCmltcG9ydCBzeXMKClJFQ0lQSUVOVCA9ICc0ODRDRjM5Q0UzN0EwMjg4NDQ5N0FEOUM0MUExNzEwMkQyODQyRUNFJwpBUFBTID0gKCd2NzktaHViJywgJ3Y3OS10aXF1ZXQtbWFuYWdlcicsICd2NzktYnVzaW5lc3MtYWdlbnQnKQpJTUFHRVMgPSB7CiAgICAndjc5LWh1Yic6ICdzaGEyNTY6ZDcyMmYzNTcyMDZmZWM5MzhlY2E2OTFjOTJkZGZlNTdlY2U2MjgxMWY2MjEyNGY2ZmJmNzYwMjU4YjJiNjk0MCcsCiAgICAndjc5LXRpcXVldC1tYW5hZ2VyJzogJ3NoYTI1NjoxOGZjNjdmODJlYzNkYzMzYTdiMjgxZGE3OWQ2YWI4ZTZiMTdmMjk4M2Y0MTk4MzNiZDAwODEwMWQ1NzExZmMzJywKICAgICd2NzktYnVzaW5lc3MtYWdlbnQnOiAnc2hhMjU2OjFiYTI2ZDIyMDU1YjUzZGM5OTI3ODY3M2I3NzRlNDgwMDA2MTQzZjgwMjIyNTA5YTMyNTVlNzVkNTQ1MjZmNGInLAogICAgJ3Y3OS1odWItcG9zdGdyZXMnOiAnc2hhMjU2OmIwZjk1NjBhMmRlMDgzZTJjYzczODJlNzVmODA4YzczODFhMzI4NTJhN2VjNDkxMTdkZWVkYjMwMGU1NTJiMjQnLAogICAgJ3RpcXVldC1wb3N0Z3Jlcyc6ICdzaGEyNTY6Y2Y3OGU3NjY4M2I5Y2E4YzU3MzNjYmJkY2U2YzkyNjJiNDViNjc2NzkzNGRkMGE5NWU2NzFmOWEwZmMyMDY4NScsCn0KSE9TVF9TVEFURSA9ICgKICAgICcuY29uZmlnL3Y3OS13b3JrZm9yY2UvZ29vZ2xlJywKICAgICcubG9jYWwvc2hhcmUvdjc5LXdvcmtmb3JjZS1vcGVyYXRpb25zJywKICAgICcubG9jYWwvc2hhcmUvdjc5LWFwcHJvdmVkLXRhc2std29ya2VyJywKKQpTVEFHRSA9ICdTVEFSVCcKCmRlZiBzdGFnZShuYW1lKToKICAgIGdsb2JhbCBTVEFHRQogICAgU1RBR0UgPSBuYW1lCgpjbGFzcyBIYWx0KEV4Y2VwdGlvbik6CiAgICBwYXNzCgpkZWYgbmVlZChvaywgY29kZSk6CiAgICBpZiBub3Qgb2s6CiAgICAgICAgcmFpc2UgSGFsdChjb2RlKQoKZGVmIGNhbGwoYXJncywgZGF0YT1Ob25lLCB0aW1lb3V0PTQ1KToKICAgIHRyeToKICAgICAgICBwID0gc3VicHJvY2Vzcy5ydW4oYXJncywgaW5wdXQ9ZGF0YSwgc3Rkb3V0PXN1YnByb2Nlc3MuUElQRSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgc3RkZXJyPXN1YnByb2Nlc3MuREVWTlVMTCwgdGltZW91dD10aW1lb3V0KQogICAgZXhjZXB0IChPU0Vycm9yLCBzdWJwcm9jZXNzLlRpbWVvdXRFeHBpcmVkKToKICAgICAgICByYWlzZSBIYWx0KCdSRUFEX0NPTU1BTkRfVU5BVkFJTEFCTEUnKSBmcm9tIE5vbmUKICAgIG5lZWQocC5yZXR1cm5jb2RlID09IDAsICdSRUFEX0NPTU1BTkRfRkFJTEVEX05PX1NFQ1JFVF9PVVRQVVQnKQogICAgcmV0dXJuIHAuc3Rkb3V0CgpkZWYgamNhbGwoYXJncyk6CiAgICByZXR1cm4ganNvbi5sb2FkcyhjYWxsKGFyZ3MpKQoKZGVmIHZhbHVlcyhvKToKICAgIHJldHVybiBkaWN0KHguc3BsaXQoJz0nLCAxKSBmb3IgeCBpbiBvWydDb25maWcnXS5nZXQoJ0VudicsIFtdKSBpZiAnPScgaW4geCkKCmRlZiBsb2NhbF9kb2NrZXIoaG9zdCk6CiAgICBuZWVkKG5vdCBvcy5lbnZpcm9uLmdldCgnRE9DS0VSX0hPU1QnKSBhbmQgbm90IG9zLmVudmlyb24uZ2V0KCdET0NLRVJfQ09OVEVYVCcpLCAnRE9DS0VSX09WRVJSSURFJykKICAgIGN0eCA9IGpjYWxsKFsnZG9ja2VyJywgJ2NvbnRleHQnLCAnaW5zcGVjdCddKQogICAgbmVlZChsZW4oY3R4KSA9PSAxIGFuZCBjdHhbMF1bJ0VuZHBvaW50cyddWydkb2NrZXInXVsnSG9zdCddIGluCiAgICAgICAgICgndW5peDovLy92YXIvcnVuL2RvY2tlci5zb2NrJywgJ3VuaXg6Ly8vcnVuL2RvY2tlci5zb2NrJyksICdET0NLRVJfTk9UX0xPQ0FMJykKICAgIG5lZWQoY2FsbChbJ2RvY2tlcicsICdpbmZvJywgJy0tZm9ybWF0JywgJ3t7Lk5hbWV9fSddKS5kZWNvZGUoKS5zdHJpcCgpID09IGhvc3QsICdET0NLRVJfREFFTU9OX0hPU1RfTUlTTUFUQ0gnKQoKZGVmIG1lbW9yeV9hdmFpbGFibGUoKToKICAgIGZvciBsaW5lIGluIFBhdGgoJy9wcm9jL21lbWluZm8nKS5yZWFkX3RleHQoKS5zcGxpdGxpbmVzKCk6CiAgICAgICAgaWYgbGluZS5zdGFydHN3aXRoKCdNZW1BdmFpbGFibGU6Jyk6CiAgICAgICAgICAgIHJldHVybiBpbnQobGluZS5zcGxpdCgpWzFdKSAqIDEwMjQKICAgIHJldHVybiAwCgpkZWYgb3ZlcmxhcChhLCBiKToKICAgIHJldHVybiBvcy5wYXRoLmNvbW1vbnBhdGgoW2EsIGJdKSBpbiAoYSwgYikKCmRlZiBwcml2YXRlX21ldGFkYXRhKHBhdGgpOgogICAgdHJ5OgogICAgICAgIHMgPSBwYXRoLmxzdGF0KCkKICAgICAgICByZXR1cm4geydwcmVzZW50JzogVHJ1ZSwgJ3JlZ3VsYXInOiBzdGF0LlNfSVNSRUcocy5zdF9tb2RlKSwKICAgICAgICAgICAgICAgICdkaXJlY3RvcnknOiBzdGF0LlNfSVNESVIocy5zdF9tb2RlKSwgJ293bmVkJzogcy5zdF91aWQgPT0gb3MuZ2V0dWlkKCksCiAgICAgICAgICAgICAgICAncHJpdmF0ZSc6IG5vdCAoc3RhdC5TX0lNT0RFKHMuc3RfbW9kZSkgJiAwbzA3Nyl9CiAgICBleGNlcHQgRmlsZU5vdEZvdW5kRXJyb3I6CiAgICAgICAgcmV0dXJuIHsncHJlc2VudCc6IEZhbHNlfQoKCkVYUEVDVEVEX0hVQl9TT1VSQ0VTPXsnL2hvbWUvZmlyZWxpb24vLnY3OS1oYXJkZW5lZC1wYWlyLXJlbGVhc2VzL3BhaXItMjAyNjEwMjVUMjA0MzUwWi03YTkzZmY0ZTZiZTAvdjc5LWh1Yi1yb2xsYmFjay5qc29uJzonY2NiOGRkNDAyNzE1OTYxNTQyMWM2Nzg2MWMyYTRhZmY1OTE1NWYyZjM4YjBhNzFiYWZlMTNiZTZiNWY4ZDVlMSd9CkVYUEVDVEVEX01PVU5UUz17CiAndjc5LWh1Yic6eycvYXBwL2RhdGEnOignYmluZCcsVHJ1ZSksJy9ydW4vdjc5LXdvcmtmb3JjZS1yZXBvcnRzJzooJ2JpbmQnLEZhbHNlKSwnL3J1bi9zZWNyZXRzL3Y3OS1hZ2VudC10b2tlbic6KCdiaW5kJyxGYWxzZSksJy9ydW4vc2VjcmV0cy92NzktY29vLWdpdGh1Yi10b2tlbic6KCdiaW5kJyxGYWxzZSksJy9ydW4vc2VjcmV0cy92NzktcmVhZG9ubHktcGxhdGZvcm0tdG9rZW4nOignYmluZCcsRmFsc2UpLCcvcnVuL3NlY3JldHMvdjc5LXdvcmtmb3JjZS10b2tlbic6KCdiaW5kJyxGYWxzZSksJy9ydW4vdjc5LWdvb2dsZSc6KCd2b2x1bWUnLEZhbHNlKX0sCiAndjc5LXRpcXVldC1tYW5hZ2VyJzp7Jy9hcHAvZGF0YSc6KCd2b2x1bWUnLFRydWUpLCcvYXBwL3VwbG9hZHMnOigndm9sdW1lJyxUcnVlKX0sCiAndjc5LWJ1c2luZXNzLWFnZW50Jzp7Jy9ydW4vc2VjcmV0cy92NzktYWdlbnQtdG9rZW4nOignYmluZCcsRmFsc2UpfSwKfQpQUklDSU5HX1BST0JFPXIiIiIKaW1wb3J0IGZzIGZyb20gJ25vZGU6ZnMnO2ltcG9ydCBwYXRoIGZyb20gJ25vZGU6cGF0aCc7aW1wb3J0IGNyeXB0byBmcm9tICdub2RlOmNyeXB0byc7CmltcG9ydCB7Y3JlYXRlUHJpY2luZ1JlcXVlc3RTdG9yZX0gZnJvbSAnLi9zZXJ2ZXIvcHJpY2luZy1yZXF1ZXN0LXN0b3JlLm1qcyc7CmltcG9ydCB7Z2V0V2lwYXlDb25maWd9IGZyb20gJy4vc2VydmVyL3dpcGF5LXByb3ZpZGVyLm1qcyc7CnRyeXsKY29uc3QgcmF3PWZzLnJlYWRGaWxlU3luYygnL2FwcC9zZXJ2ZXIudHMnKTtpZihjcnlwdG8uY3JlYXRlSGFzaCgnc2hhMScpLnVwZGF0ZShCdWZmZXIuZnJvbSgnYmxvYiAnK3Jhdy5sZW5ndGgrJ1wwJykpLnVwZGF0ZShyYXcpLmRpZ2VzdCgnaGV4JykhPT0nNjc4NGRlZjlhMzhkMDE4Zjg3YWE4NWUwZDczZWMxMGQ2NTk3MmRhZicpcHJvY2Vzcy5leGl0KDIpOwpjb25zdCBmaWxlPXBhdGgucmVzb2x2ZShwcm9jZXNzLmVudi5EQVRBX0RJUnx8Jy9hcHAvZGF0YScsJ3ByaWNpbmctcmVxdWVzdHMtdjEuanNvbicpO2NvbnN0IHN0PWZzLmxzdGF0U3luYyhmaWxlKTsKaWYoIXN0LmlzRmlsZSgpfHwoc3QubW9kZSYwbzA3Nyl8fGZzLmV4aXN0c1N5bmMoZmlsZSsnLmxvY2snKXx8Z2V0V2lwYXlDb25maWcoKS5lbnZpcm9ubWVudCE9PSdzYW5kYm94Jylwcm9jZXNzLmV4aXQoMyk7CmNvbnN0IHNlY3JldD1TdHJpbmcocHJvY2Vzcy5lbnYuVjc5X0hVQl9TRUNVUklUWV9LRVl8fHByb2Nlc3MuZW52LlY3OV9QTEFURk9STV9TSEFSRURfU0VDUkVUfHwnJykudHJpbSgpOwpjb25zdCBzdGF0ZT1hd2FpdCBjcmVhdGVQcmljaW5nUmVxdWVzdFN0b3JlKHtmaWxlLHNlY3JldH0pLnJlYWQoKTsKY29uc29sZS5sb2coSlNPTi5zdHJpbmdpZnkoe3ByZXNlbnQ6dHJ1ZSxwcml2YXRlOnRydWUsc2lnbmF0dXJlVmVyaWZpZWQ6dHJ1ZSxyZXF1ZXN0czpzdGF0ZS5yZXF1ZXN0cy5sZW5ndGgsZXZlbnRzOnN0YXRlLmV2ZW50cy5sZW5ndGgsd2lwYXlTYW5kYm94OnRydWUsc291cmNlUGlubmVkOnRydWV9KSk7Cn1jYXRjaHtwcm9jZXNzLmV4aXQoNCl9CiIiIgpkZWYgdmFsaWRhdGVfZmluYWxfc2NvcGUocmVwb3J0LHNlbGVjdGVkKToKIGZvciBhcHAsZXhwZWN0ZWQgaW4gRVhQRUNURURfTU9VTlRTLml0ZW1zKCk6CiAgcm93PXNlbGVjdGVkW2FwcF07YWN0dWFsPXttWydEZXN0aW5hdGlvbiddOihtWydUeXBlJ10sbVsnUlcnXSkgZm9yIG0gaW4gcm93WydNb3VudHMnXX0KICBuZWVkKGFjdHVhbD09ZXhwZWN0ZWQsJ0ZJTkFMX0FQUExJQ0FUSU9OX01PVU5UX1NDT1BFX0RJRkZFUlMnKQogIGlmIGFwcD09J3Y3OS1odWInOgogICBwYXRocz1yb3dbJ0NvbmZpZyddWydMYWJlbHMnXVsnY29tLmRvY2tlci5jb21wb3NlLnByb2plY3QuY29uZmlnX2ZpbGVzJ10uc3BsaXQoJywnKQogICBuZWVkKHNldChwYXRocyk9PXNldChFWFBFQ1RFRF9IVUJfU09VUkNFUyksJ0ZJTkFMX0hVQl9DT01QT1NFX0NIQUlOX0RJRkZFUlMnKQogICBuZWVkKGFsbChyZXBvcnRbJ2NvbXBvc2VfaW5wdXRfaGFzaGVzJ10uZ2V0KHApPT1kaWdlc3QgZm9yIHAsZGlnZXN0IGluIEVYUEVDVEVEX0hVQl9TT1VSQ0VTLml0ZW1zKCkpLCdGSU5BTF9IVUJfQ09NUE9TRV9IQVNIX0RJRkZFUlMnKQogICBnb29nbGU9bmV4dChtIGZvciBtIGluIHJvd1snTW91bnRzJ10gaWYgbVsnRGVzdGluYXRpb24nXT09Jy9ydW4vdjc5LWdvb2dsZScpCiAgIG5lZWQoZ29vZ2xlLmdldCgnTmFtZScpPT0ndjc5LWdvb2dsZS1jcmVkZW50aWFscy00OWY4MTM3NzY3NWEnLCdHT09HTEVfQ1JFREVOVElBTF9WT0xVTUVfRElGRkVSUycpCiBtZXRhZGF0YT1qc29uLmxvYWRzKGNhbGwoWydkb2NrZXInLCdleGVjJywndjc5LWh1YicsJ25vZGUnLCctLWlucHV0LXR5cGU9bW9kdWxlJywnLWUnLFBSSUNJTkdfUFJPQkVdKSkKIG5lZWQoYWxsKG1ldGFkYXRhLmdldChrKSBpcyBUcnVlIGZvciBrIGluICgncHJlc2VudCcsJ3ByaXZhdGUnLCdzaWduYXR1cmVWZXJpZmllZCcsJ3dpcGF5U2FuZGJveCcsJ3NvdXJjZVBpbm5lZCcpKSwnUFJJQ0lOR19MRURHRVJfT1JfU0FOREJPWF9DSEVDS19GQUlMRUQnKQogbmVlZChpc2luc3RhbmNlKG1ldGFkYXRhLmdldCgncmVxdWVzdHMnKSxpbnQpIGFuZCBtZXRhZGF0YVsncmVxdWVzdHMnXT49MSwnQUNDRVBURURfUFJJQ0lOR19SRVFVRVNUX05PVF9GT1VORCcpCiByZXBvcnRbJ3ByaWNpbmdfbGVkZ2VyX21ldGFkYXRhJ109bWV0YWRhdGEKIHJlcG9ydFsnbW91bnRfY291bnQnXT1zdW0obGVuKHYpIGZvciB2IGluIEVYUEVDVEVEX01PVU5UUy52YWx1ZXMoKSkKIHJlcG9ydFsnZXhwZWN0ZWRfZW5jcnlwdGVkX2FydGlmYWN0cyddPTUrcmVwb3J0Wydtb3VudF9jb3VudCddCiByZXBvcnRbJ2N1cnJlbnRfaHViX3NvdXJjZSddPSc5NTI4ZjI3NDIyNTI1ZWQ2MzQwYzZhNDJlMDE1MmFhNjJmNDMzZmQ4JwogcmVwb3J0Wydtb3VudGVkX2dvb2dsZV9jcmVkZW50aWFsc19jb250ZW50c19yZWFkJ109RmFsc2UKIHJlcG9ydFsnZmluYWxfcmVjb3Zlcnlfc2NvcGUnXT0nRklWRV9DVVJSRU5UX0lNQUdFU19UV09fREFUQUJBU0VTX1RFTl9NT1VOVFNfUFJJVkFURV9IT1NUX1NUQVRFJwoKZGVmIHNlcnZlcigpOgogICAgc3RhZ2UoJ1NFUlZFUl9JREVOVElUWV9BTkRfRE9DS0VSJykKICAgIG5lZWQoc29ja2V0LmdldGhvc3RuYW1lKCkgPT0gJ3Y3OXNsJyBhbmQgb3MuZ2V0ZXVpZCgpICE9IDAgYW5kCiAgICAgICAgIFBhdGguaG9tZSgpID09IFBhdGgoJy9ob21lL2ZpcmVsaW9uJyksICdXUk9OR19TRVJWRVJfVVNFUicpCiAgICBsb2NhbF9kb2NrZXIoJ3Y3OXNsJykKICAgIG5hbWVzID0gY2FsbChbJ2RvY2tlcicsICdwcycsICctLWFsbCcsICctLWZvcm1hdCcsICd7ey5OYW1lc319J10pLmRlY29kZSgpLnNwbGl0bGluZXMoKQogICAgcm93cyA9IGpjYWxsKFsnZG9ja2VyJywgJ2luc3BlY3QnLCAqbmFtZXNdKQogICAgYWxsX3Jvd3MgPSB7clsnTmFtZSddLmxzdHJpcCgnLycpOiByIGZvciByIGluIHJvd3N9CiAgICBuZWVkKHNldChJTUFHRVMpIDw9IHNldChhbGxfcm93cyksICdSRVFVSVJFRF9DT05UQUlORVJfQUJTRU5UJykKICAgIHNlbGVjdGVkID0ge246IGFsbF9yb3dzW25dIGZvciBuIGluIElNQUdFU30KICAgIGJsb2NrZXJzLCBwaW5zLCBjb21wb3NlX2lucHV0cywgbW91bnRzID0gW10sIHt9LCB7fSwgW10KICAgIGltYWdlX2J5dGVzID0gMAogICAgZm9yIG5hbWUsIG8gaW4gc2VsZWN0ZWQuaXRlbXMoKToKICAgICAgICBzdGFnZSgnU0VSVkVSX0NPTlRBSU5FUl8nICsgbmFtZS5yZXBsYWNlKCctJywgJ18nKS51cHBlcigpKQogICAgICAgIGhlYWx0aHkgPSBvWydTdGF0ZSddLmdldCgnUnVubmluZycpIGFuZCBvWydTdGF0ZSddLmdldCgnSGVhbHRoJywge30pLmdldCgnU3RhdHVzJykgPT0gJ2hlYWx0aHknCiAgICAgICAgbmVlZChvWydJbWFnZSddID09IElNQUdFU1tuYW1lXSBhbmQgaGVhbHRoeSwgJ1BJTk5FRF9JTUFHRV9PUl9IRUFMVEhfQ0hBTkdFRCcpCiAgICAgICAgcGluc1tuYW1lXSA9IHsnaWQnOiBvWydJZCddLCAnaW1hZ2UnOiBvWydJbWFnZSddLCAnaGVhbHRoeSc6IFRydWV9CiAgICAgICAgaW1hZ2VfYnl0ZXMgKz0gamNhbGwoWydkb2NrZXInLCAnaW1hZ2UnLCAnaW5zcGVjdCcsIG9bJ0ltYWdlJ11dKVswXVsnU2l6ZSddCiAgICAgICAgbGFiZWxzID0gb1snQ29uZmlnJ10uZ2V0KCdMYWJlbHMnKSBvciB7fQogICAgICAgIHBhdGhzID0gbGFiZWxzLmdldCgnY29tLmRvY2tlci5jb21wb3NlLnByb2plY3QuY29uZmlnX2ZpbGVzJywgJycpLnNwbGl0KCcsJykKICAgICAgICBuZWVkKGFsbChwLnN0YXJ0c3dpdGgoJy8nKSBmb3IgcCBpbiBwYXRocyksICdDT01QT1NFX0NIQUlOX1VOQVZBSUxBQkxFJykKICAgICAgICBmb3IgdGV4dCBpbiBwYXRoczoKICAgICAgICAgICAgcCA9IFBhdGgodGV4dCkKICAgICAgICAgICAgcyA9IHAubHN0YXQoKQogICAgICAgICAgICBuZWVkKHN0YXQuU19JU1JFRyhzLnN0X21vZGUpIGFuZCBzLnN0X3NpemUgPD0gMioxMDI0KioyIGFuZAogICAgICAgICAgICAgICAgIHMuc3RfdWlkIGluICgwLCBvcy5nZXR1aWQoKSkgYW5kIG5vdCBzLnN0X21vZGUgJiAwbzAwMiwgJ0NPTVBPU0VfSU5QVVRfVU5TQUZFJykKICAgICAgICAgICAgY29tcG9zZV9pbnB1dHNbdGV4dF0gPSBoYXNobGliLnNoYTI1NihwLnJlYWRfYnl0ZXMoKSkuaGV4ZGlnZXN0KCkKICAgICAgICBpZiBuYW1lIGluIEFQUFM6CiAgICAgICAgICAgIGZvciBtIGluIG8uZ2V0KCdNb3VudHMnLCBbXSk6CiAgICAgICAgICAgICAgICBuZWVkKG1bJ1R5cGUnXSBpbiAoJ2JpbmQnLCAndm9sdW1lJykgYW5kIG0uZ2V0KCdTb3VyY2UnLCAnJykuc3RhcnRzd2l0aCgnLycpLCAnTU9VTlRfVFlQRV9VTlJFVklFV0VEJykKICAgICAgICAgICAgICAgIHNvdXJjZSA9IG1bJ1NvdXJjZSddCiAgICAgICAgICAgICAgICBzaGFyZWQgPSBbXQogICAgICAgICAgICAgICAgZm9yIG90aGVyLCBmb3JlaWduIGluIGFsbF9yb3dzLml0ZW1zKCk6CiAgICAgICAgICAgICAgICAgICAgaWYgb3RoZXIgaW4gQVBQUyBvciBub3QgZm9yZWlnblsnU3RhdGUnXS5nZXQoJ1J1bm5pbmcnKToKICAgICAgICAgICAgICAgICAgICAgICAgY29udGludWUKICAgICAgICAgICAgICAgICAgICBmb3IgZm0gaW4gZm9yZWlnbi5nZXQoJ01vdW50cycsIFtdKToKICAgICAgICAgICAgICAgICAgICAgICAgaWYgZm0uZ2V0KCdSVycpIGFuZCBmbS5nZXQoJ1NvdXJjZScpIGFuZCBvdmVybGFwKHNvdXJjZSwgZm1bJ1NvdXJjZSddKToKICAgICAgICAgICAgICAgICAgICAgICAgICAgIHNoYXJlZC5hcHBlbmQob3RoZXIpCiAgICAgICAgICAgICAgICBpZiBzaGFyZWQ6CiAgICAgICAgICAgICAgICAgICAgYmxvY2tlcnMuYXBwZW5kKCdTSEFSRURfV1JJVEVSXycgKyBuYW1lKQogICAgICAgICAgICAgICAgbW91bnRzLmFwcGVuZCh7J2NvbnRhaW5lcic6IG5hbWUsICdkZXN0aW5hdGlvbic6IG1bJ0Rlc3RpbmF0aW9uJ10sCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAndHlwZSc6IG1bJ1R5cGUnXSwgJ3J3JzogbVsnUlcnXSwgJ290aGVyX3dyaXRlcl9jb3VudCc6IGxlbihzZXQoc2hhcmVkKSl9KQogICAgaCwgdCA9IHZhbHVlcyhzZWxlY3RlZFsndjc5LWh1YiddKSwgdmFsdWVzKHNlbGVjdGVkWyd2NzktdGlxdWV0LW1hbmFnZXInXSkKICAgIHN0YWdlKCdTRVJWRVJfU0VDVVJJVFlfQU5EX1BSSUNFX0lOUFVUUycpCiAgICBuZWVkKGguZ2V0KCdWNzlfUkVRVUlSRV9BRE1JTl9NRkEnKSA9PSAnMScgYW5kCiAgICAgICAgIGguZ2V0KCdWNzlfSFVCX1RJUVVFVF9TRVNTSU9OX0JJTkRJTkcnKSA9PSAnMScgYW5kCiAgICAgICAgIHQuZ2V0KCdWNzlfVElRVUVUX1NFU1NJT05fQklORElOR19FTkFCTEVEJykgPT0gJzEnIGFuZAogICAgICAgICB0LmdldCgnVjc5X0FMTE9XX0xFR0FDWV9BVVRIJykgPT0gJzAnIGFuZAogICAgICAgICB0LmdldCgnVjc5X0VOVElUTEVNRU5UX1JFQ0hFQ0tfRU5BQkxFRCcpID09ICcxJywgJ1NFQ1VSSVRZX0ZMQUdTX0NIQU5HRUQnKQogICAgbmVlZChoLmdldCgnVjc5X1RJUVVFVF9MQVVOQ0hfU0VDUkVUJykgYW5kCiAgICAgICAgIGhbJ1Y3OV9USVFVRVRfTEFVTkNIX1NFQ1JFVCddID09IHQuZ2V0KCdWNzlfVElRVUVUX0xBVU5DSF9TRUNSRVQnKSwgJ1NTT19TRUNSRVRfTUlTTUFUQ0gnKQogICAgcHJpY2VfaW5wdXRzX3ByZXNlbnQgPSBhbGwodC5nZXQoJ1BMQU5fUFJJQ0VfJyArIHgpIGZvciB4IGluICgnU1RBUlRFUicsJ1BSTycsJ0VOVEVSUFJJU0UnKSkKICAgIGlmIG5vdCBwcmljZV9pbnB1dHNfcHJlc2VudDoKICAgICAgICBibG9ja2Vycy5hcHBlbmQoJ0ZST1pFTl9QUklDRV9JTlBVVF9BQlNFTlQnKQogICAgZGJfdmVyc2lvbnMgPSB7fQogICAgZm9yIGRiLCBtYWpvciBpbiBbKCd2NzktaHViLXBvc3RncmVzJywgJzE3JyksICgndGlxdWV0LXBvc3RncmVzJywgJzE2JyldOgogICAgICAgIHN0YWdlKCdTRVJWRVJfREFUQUJBU0VfJyArIG1ham9yKQogICAgICAgIHZlcnNpb24gPSBjYWxsKFsnZG9ja2VyJywnZXhlYycsZGIsJ3BnX2R1bXAnLCctLXZlcnNpb24nXSkuZGVjb2RlKCkKICAgICAgICBuZWVkKHJlLnNlYXJjaChyJ1Bvc3RncmVTUUxcKSAnK21ham9yK3InXC4nLCB2ZXJzaW9uKSwgJ1BHX0RVTVBfVkVSU0lPTl9DSEFOR0VEJykKICAgICAgICBjYWxsKFsnZG9ja2VyJywnZXhlYycsZGIsJ3NoJywnLWMnLAogICAgICAgICAgICAgICdwZ19pc3JlYWR5IC1xIC1VICIke1BPU1RHUkVTX1VTRVI6LXBvc3RncmVzfSIgLWQgIiR7UE9TVEdSRVNfREI6LSR7UE9TVEdSRVNfVVNFUjotcG9zdGdyZXN9fSInXSkKICAgICAgICBkYl92ZXJzaW9uc1tkYl0gPSB7J21ham9yJzogbWFqb3IsICdyZWFkeSc6IFRydWV9CiAgICB0aW1lcnMgPSBbXQogICAgc3RhZ2UoJ1NFUlZFUl9USU1FUlNfQU5EX0hPU1RfU1RBVEUnKQogICAgbGlzdGluZyA9IGNhbGwoWydzeXN0ZW1jdGwnLCctLXVzZXInLCdsaXN0LXVuaXRzJywnLS10eXBlPXRpbWVyJywnLS1zdGF0ZT1hY3RpdmUnLCctLW5vLWxlZ2VuZCcsJy0tcGxhaW4nXSkuZGVjb2RlKCkKICAgIGZvciBsaW5lIGluIGxpc3Rpbmcuc3BsaXRsaW5lcygpOgogICAgICAgIHVuaXQgPSBsaW5lLnNwbGl0KClbMF0KICAgICAgICBpZiByZS5mdWxsbWF0Y2gocid2NzlbLUEtWmEtejAtOUBfLl0rXC50aW1lcicsIHVuaXQpIGFuZCByZS5zZWFyY2gocid3b3JrZm9yY2V8cmVsZWFzZXx0YXNrJywgdW5pdCk6CiAgICAgICAgICAgIHRpbWVycy5hcHBlbmQodW5pdCkKICAgIGhvc3Rfc3RhdGUgPSB7cDogcHJpdmF0ZV9tZXRhZGF0YShQYXRoLmhvbWUoKS9wKSBmb3IgcCBpbiBIT1NUX1NUQVRFfQogICAgZm9yIHAsIG1ldGEgaW4gaG9zdF9zdGF0ZS5pdGVtcygpOgogICAgICAgIGlmIG5vdCBtZXRhLmdldCgncHJlc2VudCcpIG9yIG5vdCBtZXRhLmdldCgnZGlyZWN0b3J5Jykgb3Igbm90IG1ldGEuZ2V0KCdvd25lZCcpOgogICAgICAgICAgICBibG9ja2Vycy5hcHBlbmQoJ0hPU1RfU1RBVEVfVU5TQUZFXycgKyBwLnJzcGxpdCgnLycsMSlbLTFdKQogICAgZ29vZ2xlID0ge246IHByaXZhdGVfbWV0YWRhdGEoUGF0aC5ob21lKCkvSE9TVF9TVEFURVswXS9uKSBmb3IgbiBpbiAoJ2NsaWVudC5qc29uJywnY3JlZGVudGlhbHMuanNvbicpfQogICAgaWYgbm90IGFsbChtLmdldCgncmVndWxhcicpIGFuZCBtLmdldCgnb3duZWQnKSBhbmQgbS5nZXQoJ3ByaXZhdGUnKSBmb3IgbSBpbiBnb29nbGUudmFsdWVzKCkpOgogICAgICAgIGJsb2NrZXJzLmFwcGVuZCgnR09PR0xFX0NSRURFTlRJQUxfRklMRV9VTlNBRkUnKQogICAgIyBJbnNwZWN0IG1ldGFkYXRhIG9ubHk7IGRvIG5vdCByZWFkIGNyZWRlbnRpYWxzIG9yIHF1ZXVlIHBheWxvYWRzLgogICAgd29ya2ZvcmNlX3VuaXRzID0gW10KICAgIHVuaXRfcm9vdCA9IFBhdGguaG9tZSgpLycuY29uZmlnL3N5c3RlbWQvdXNlcicKICAgIGlmIHVuaXRfcm9vdC5pc19kaXIoKToKICAgICAgICB3b3JrZm9yY2VfdW5pdHMgPSBzb3J0ZWQocC5uYW1lIGZvciBwIGluIHVuaXRfcm9vdC5pdGVyZGlyKCkKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBpZiBwLmlzX2ZpbGUoKSBhbmQgcmUuZnVsbG1hdGNoKHIndjc5Wy1BLVphLXowLTlAXy5dK1wuKHNlcnZpY2V8dGltZXIpJyxwLm5hbWUpCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgYW5kIHJlLnNlYXJjaChyJ3dvcmtmb3JjZXxyZWxlYXNlfHRhc2snLHAubmFtZSkpCiAgICBsb2NrID0gUGF0aC5ob21lKCkvJy52NzktcG9ydGZvbGlvLXJvbGxvdXQubG9jaycKICAgIGlmIGxvY2suZXhpc3RzKCk6CiAgICAgICAgbmVlZChub3QgbG9jay5pc19zeW1saW5rKCkgYW5kIGxvY2suaXNfZmlsZSgpLCAnT1BFUkFUSU9OX0xPQ0tfVU5TQUZFJykKICAgICAgICB3aXRoIGxvY2sub3BlbigncmInKSBhcyBmOgogICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICBmY250bC5mbG9jayhmLCBmY250bC5MT0NLX0VYIHwgZmNudGwuTE9DS19OQikKICAgICAgICAgICAgICAgIGZjbnRsLmZsb2NrKGYsIGZjbnRsLkxPQ0tfVU4pCiAgICAgICAgICAgIGV4Y2VwdCBCbG9ja2luZ0lPRXJyb3I6CiAgICAgICAgICAgICAgICBibG9ja2Vycy5hcHBlbmQoJ09USEVSX1JFTEVBU0VfT1BFUkFUSU9OX1JVTk5JTkcnKQogICAgZm9yIG4gaW4gc2VsZWN0ZWQ6CiAgICAgICAgY3VycmVudCA9IGpjYWxsKFsnZG9ja2VyJywnaW5zcGVjdCcsbl0pWzBdCiAgICAgICAgbmVlZChjdXJyZW50WydJZCddID09IHNlbGVjdGVkW25dWydJZCddIGFuZCBjdXJyZW50WydJbWFnZSddID09IHNlbGVjdGVkW25dWydJbWFnZSddLCAnUlVOVElNRV9DSEFOR0VEX0RVUklOR19QUkVGTElHSFQnKQogICAgcmVzdWx0ID0geydtb2RlJzogJ1JFQURfT05MWV9DSEVDS1BPSU5UX1JFQURJTkVTUycsICdjaGVja2VkX2F0JzogZGF0ZXRpbWUuZGF0ZXRpbWUubm93KGRhdGV0aW1lLnRpbWV6b25lLnV0YykuaXNvZm9ybWF0KCksCiAgICAgICAgICAgICAgJ3BpbnMnOiBwaW5zLCAnY29tcG9zZV9pbnB1dF9oYXNoZXMnOiBjb21wb3NlX2lucHV0cywgJ2FwcF9tb3VudHMnOiBtb3VudHMsCiAgICAgICAgICAgICAgJ2ltYWdlX2J5dGVzJzogaW1hZ2VfYnl0ZXMsICdzZXJ2ZXJfZnJlZV9ieXRlcyc6IHNodXRpbC5kaXNrX3VzYWdlKFBhdGguaG9tZSgpKS5mcmVlLAogICAgICAgICAgICAgICdzZXJ2ZXJfYXZhaWxhYmxlX21lbW9yeV9ieXRlcyc6IG1lbW9yeV9hdmFpbGFibGUoKSwgJ2RhdGFiYXNlcyc6IGRiX3ZlcnNpb25zLAogICAgICAgICAgICAgICdhY3RpdmVfdGltZXJzX3RvX3F1aWVzY2UnOiBzb3J0ZWQodGltZXJzKSwgJ3dvcmtmb3JjZV91bml0X2ZpbGVzJzogd29ya2ZvcmNlX3VuaXRzLAogICAgICAgICAgICAgICdob3N0X3N0YXRlX21ldGFkYXRhJzogaG9zdF9zdGF0ZSwgJ2dvb2dsZV9maWxlX21ldGFkYXRhJzogZ29vZ2xlLAogICAgICAgICAgICAgICdmcm96ZW5fcHJpY2VfaW5wdXRzX2F2YWlsYWJsZV9ub3RfcHJpbnRlZCc6IGJvb2wocHJpY2VfaW5wdXRzX3ByZXNlbnQpLAogICAgICAgICAgICAgICdnb29nbGVfY29udGVudHNfcmVhZCc6IEZhbHNlLCAncHJvZHVjdGlvbl9jaGFuZ2VkJzogRmFsc2UsCiAgICAgICAgICAgICAgJ2Jsb2NrZXJzJzogc29ydGVkKHNldChibG9ja2VycykpLCAnY2FwdHVyZV9wZXJmb3JtZWQnOiBGYWxzZSwgJ3Jlc3RvcmVfcGVyZm9ybWVkJzogRmFsc2V9CiAgICB2YWxpZGF0ZV9maW5hbF9zY29wZShyZXN1bHQsc2VsZWN0ZWQpCiAgICByZXN1bHRbJ2ludmVudG9yeV9zaGEyNTYnXSA9IGhhc2hsaWIuc2hhMjU2KGpzb24uZHVtcHMoCiAgICAgICAgeydwaW5zJzogcGlucywgJ2lucHV0cyc6IGNvbXBvc2VfaW5wdXRzLCAndGltZXJzJzogc29ydGVkKHRpbWVycyksICdtb3VudHMnOiBtb3VudHMsICdmaW5hbF9zY29wZSc6cmVzdWx0WydmaW5hbF9yZWNvdmVyeV9zY29wZSddfSwKICAgICAgICBzb3J0X2tleXM9VHJ1ZSkuZW5jb2RlKCkpLmhleGRpZ2VzdCgpCiAgICByZXR1cm4gcmVzdWx0CgpkZWYgYWNlcigpOgogICAgc3RhZ2UoJ0FDRVJfSURFTlRJVFlfQU5EX0RPQ0tFUicpCiAgICBuZWVkKHNvY2tldC5nZXRob3N0bmFtZSgpID09ICdmaXJlbGlvbi1Bc3BpcmUtQTMxNS01MScgYW5kIG9zLmdldGV1aWQoKSAhPSAwLCAnUlVOX09OX05PTlJPT1RfQUNFUicpCiAgICBsb2NhbF9kb2NrZXIoc29ja2V0LmdldGhvc3RuYW1lKCkpCiAgICBzdGFnZSgnQUNFUl9SRUNPVkVSWV9LRVlfTUVUQURBVEEnKQogICAgZmluZ2VycHJpbnRzID0gY2FsbChbJ2dwZycsJy0tYmF0Y2gnLCctLXdpdGgtY29sb25zJywnLS1maW5nZXJwcmludCcsUkVDSVBJRU5UXSkuZGVjb2RlKCkKICAgIG5lZWQoJ2Zwcjo6Ojo6Ojo6OicrUkVDSVBJRU5UKyc6JyBpbiBmaW5nZXJwcmludHMsICdSRUNPVkVSWV9QVUJMSUNfS0VZX1VOQVZBSUxBQkxFJykKICAgIGtleXMgPSBjYWxsKFsnZ3BnJywnLS1iYXRjaCcsJy0td2l0aC1jb2xvbnMnLCctLWxpc3Qtc2VjcmV0LWtleXMnLFJFQ0lQSUVOVF0pLmRlY29kZSgpCiAgICBuZWVkKGFueShsaW5lLnN0YXJ0c3dpdGgoJ3NlYzonKSBvciBsaW5lLnN0YXJ0c3dpdGgoJ3NlYyM6JykgZm9yIGxpbmUgaW4ga2V5cy5zcGxpdGxpbmVzKCkpLCAnUkVDT1ZFUllfUFJJVkFURV9LRVlfVU5BVkFJTEFCTEUnKQogICAgcHJpbnQoJ0FDRVJfUkVDT1ZFUllfS0VZPVBJTk5FRF9QVUJMSUNfQU5EX1BSSVZBVEVfUFJFU0VOVCcsIGZsdXNoPVRydWUpCiAgICBwcmludCgnQUNFUl9GUkVFX0JZVEVTPScrc3RyKHNodXRpbC5kaXNrX3VzYWdlKFBhdGguaG9tZSgpKS5mcmVlKSwgZmx1c2g9VHJ1ZSkKICAgIHByaW50KCdBQ0VSX0FWQUlMQUJMRV9NRU1PUllfQllURVM9JytzdHIobWVtb3J5X2F2YWlsYWJsZSgpKSwgZmx1c2g9VHJ1ZSkKICAgIGNvbW1hbmQgPSBbJ3NzaCcsJy1UJywnLW8nLCdCYXRjaE1vZGU9eWVzJywnLW8nLCdTdHJpY3RIb3N0S2V5Q2hlY2tpbmc9eWVzJywKICAgICAgICAgICAgICAgJy1vJywnQ29ubmVjdFRpbWVvdXQ9MTAnLCdmaXJlbGlvbkB2NzlzbCcsJ3B5dGhvbjMgLUIgLSAtLXNlcnZlciddCiAgICBzdGFnZSgnU0VSVkVSX1JFQURfT05MWV9JTlZFTlRPUlknKQogICAgdHJ5OgogICAgICAgIHByb2Nlc3MgPSBzdWJwcm9jZXNzLnJ1bihjb21tYW5kLCBpbnB1dD1QYXRoKF9fZmlsZV9fKS5yZWFkX2J5dGVzKCksCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHN0ZG91dD1zdWJwcm9jZXNzLlBJUEUsIHN0ZGVycj1zdWJwcm9jZXNzLkRFVk5VTEwsIHRpbWVvdXQ9MTgwKQogICAgZXhjZXB0IChPU0Vycm9yLCBzdWJwcm9jZXNzLlRpbWVvdXRFeHBpcmVkKToKICAgICAgICByYWlzZSBIYWx0KCdTU0hfUkVBRF9VTkFWQUlMQUJMRScpIGZyb20gTm9uZQogICAgcmF3ID0gcHJvY2Vzcy5zdGRvdXQKICAgIGlmIHByb2Nlc3MucmV0dXJuY29kZToKICAgICAgICB0cnk6CiAgICAgICAgICAgIGVycm9yID0ganNvbi5sb2FkcyhyYXcpCiAgICAgICAgICAgIGZvciBrZXkgaW4gKCdlcnJvcl9zdGFnZScsICdlcnJvcicpOgogICAgICAgICAgICAgICAgaWYgcmUuZnVsbG1hdGNoKHInW0EtWjAtOV9dKycsIHN0cihlcnJvci5nZXQoa2V5LCAnJykpKToKICAgICAgICAgICAgICAgICAgICBwcmludCgnU0VSVkVSXycgKyBrZXkudXBwZXIoKSArICc9JyArIGVycm9yW2tleV0sIGZsdXNoPVRydWUpCiAgICAgICAgZXhjZXB0IChWYWx1ZUVycm9yLCBUeXBlRXJyb3IpOgogICAgICAgICAgICBwYXNzCiAgICAgICAgcmFpc2UgSGFsdCgnU0VSVkVSX1JFQURJTkVTU19GQUlMRUQnKQogICAgcmVwb3J0ID0ganNvbi5sb2FkcyhyYXcpCiAgICBuZWVkKHJlcG9ydC5nZXQoJ21vZGUnKSA9PSAnUkVBRF9PTkxZX0NIRUNLUE9JTlRfUkVBRElORVNTJywgJ1JFTU9URV9SRVBPUlRfSU5WQUxJRCcpCiAgICBwcmludChqc29uLmR1bXBzKHJlcG9ydCwgaW5kZW50PTIsIHNvcnRfa2V5cz1UcnVlKSwgZmx1c2g9VHJ1ZSkKICAgIG1pbmltdW0gPSBtYXgoMjAqMTAyNCoqMywgMipyZXBvcnRbJ2ltYWdlX2J5dGVzJ10rMTAqMTAyNCoqMykKICAgIGVub3VnaCA9IHNodXRpbC5kaXNrX3VzYWdlKFBhdGguaG9tZSgpKS5mcmVlID49IG1pbmltdW0gYW5kIHJlcG9ydFsnc2VydmVyX2ZyZWVfYnl0ZXMnXSA+PSBtaW5pbXVtCiAgICBwcmludCgnQ0hFQ0tQT0lOVF9ESVNLX0hFQURST09NPScrKCdQQVNTJyBpZiBlbm91Z2ggZWxzZSAnSU5TVUZGSUNJRU5UJyksIGZsdXNoPVRydWUpCiAgICBwcmludCgnTkVYVD1QSU5fRklOQUxfRU5DUllQVEVEX0NBUFRVUkVfQU5EX0lTT0xBVEVEX1JFU1RPUkUnLCBmbHVzaD1UcnVlKQogICAgcHJpbnQoJ0NBUFRVUkVfQU5EX1JFU1RPUkU9Tk9UX1JVTicsIGZsdXNoPVRydWUpCgpkZWYgc2VsZl90ZXN0KCk6CiAgICBhc3NlcnQgb3ZlcmxhcCgnL2EvYicsJy9hL2IvYycpIGFuZCBub3Qgb3ZlcmxhcCgnL2EvYicsJy9hL2JjJykKICAgIGFzc2VydCBsZW4oSU1BR0VTKSA9PSA1IGFuZCBsZW4oQVBQUykgPT0gMwogICAgYXNzZXJ0IGFsbChyZS5mdWxsbWF0Y2gocidzaGEyNTY6W2EtZjAtOV17NjR9JywgeCkgZm9yIHggaW4gSU1BR0VTLnZhbHVlcygpKQogICAgYXNzZXJ0IGxlbihSRUNJUElFTlQpID09IDQwCiAgICBhc3NlcnQgbm90IHByaXZhdGVfbWV0YWRhdGEoUGF0aCgnL25vbmV4aXN0ZW50LXY3OS10ZXN0LXBhdGgnKSkuZ2V0KCdwcmVzZW50JykKICAgIGltcG9ydCB0ZW1wZmlsZQogICAgd2l0aCB0ZW1wZmlsZS5UZW1wb3JhcnlEaXJlY3RvcnkoKSBhcyB0bXA6CiAgICAgICAgcD1QYXRoKHRtcCkvJ3Rlc3QnOyBwLndyaXRlX3RleHQoJ2ZpeHR1cmUnKTsgcC5jaG1vZCgwbzYwMCkKICAgICAgICBhc3NlcnQgcHJpdmF0ZV9tZXRhZGF0YShwKVsncmVndWxhciddIGFuZCBwcml2YXRlX21ldGFkYXRhKHApWydwcml2YXRlJ10KICAgICAgICBwLmNobW9kKDBvNjQ0KTsgYXNzZXJ0IG5vdCBwcml2YXRlX21ldGFkYXRhKHApWydwcml2YXRlJ10KICAgICAgICBsaW5rPVBhdGgodG1wKS8nbGluayc7IGxpbmsuc3ltbGlua190byhwKTsgYXNzZXJ0IG5vdCBwcml2YXRlX21ldGFkYXRhKGxpbmspWydyZWd1bGFyJ10KICAgIHByaW50KCdTRUxGX1RFU1Q9UEFTU19TQ09QRV9QSU5TX09WRVJMQVBfQU5EX1BSSVZBVEVfTUVUQURBVEEnKQoKCmlmIF9fbmFtZV9fID09ICdfX21haW5fXyc6CiAgICB0cnk6CiAgICAgICAgcmVwb3J0PXNlcnZlcigpCiAgICAgICAgcHJpbnQoJ0RFTU9fUkVBRElORVNTPVBBU1MnIGlmIG5vdCByZXBvcnRbJ2Jsb2NrZXJzJ10gZWxzZSAnREVNT19SRUFESU5FU1M9QkxPQ0tFRCcpCiAgICAgICAgcHJpbnQoJ05FV19JTlZFTlRPUllfU0hBMjU2PScrcmVwb3J0WydpbnZlbnRvcnlfc2hhMjU2J10pCiAgICAgICAgcHJpbnQoJ0FWQUlMQUJMRV9NRU1PUllfQllURVM9JytzdHIocmVwb3J0WydzZXJ2ZXJfYXZhaWxhYmxlX21lbW9yeV9ieXRlcyddKSkKICAgICAgICBwcmludCgnU0VSVkVSX0ZSRUVfQllURVM9JytzdHIocmVwb3J0WydzZXJ2ZXJfZnJlZV9ieXRlcyddKSkKICAgICAgICBwcmludCgnQkFDS1VQX0lNQUdFX0JZVEVTPScrc3RyKHJlcG9ydFsnaW1hZ2VfYnl0ZXMnXSkpCiAgICAgICAgcHJpbnQoJ0VOQ1JZUFRFRF9BUlRJRkFDVF9DT1VOVD0nK3N0cihyZXBvcnRbJ2V4cGVjdGVkX2VuY3J5cHRlZF9hcnRpZmFjdHMnXSkpCiAgICAgICAgcHJpbnQoJ1dPUktGT1JDRV9USU1FUlM9JysnLCcuam9pbihyZXBvcnRbJ2FjdGl2ZV90aW1lcnNfdG9fcXVpZXNjZSddKSkKICAgICAgICBwcmludCgnUkVBRElORVNTX0JMT0NLRVJfQ09ERVM9JysnLCcuam9pbihyZXBvcnRbJ2Jsb2NrZXJzJ10pKQogICAgICAgIHByaW50KCdERU1PX1JFQURJTkVTU19DSEFOR0VTPU5PTkUnKQogICAgZXhjZXB0IChIYWx0LE9TRXJyb3IsVmFsdWVFcnJvcixLZXlFcnJvcixUeXBlRXJyb3IpIGFzIGVycm9yOgogICAgICAgIHJlYXNvbj1zdHIoZXJyb3IpIGlmIGlzaW5zdGFuY2UoZXJyb3IsSGFsdCkgYW5kIHJlLmZ1bGxtYXRjaChyJ1tBLVowLTlfXSsnLHN0cihlcnJvcikpIGVsc2UgJ1JFQURJTkVTU19NRVRBREFUQV9VTkFWQUlMQUJMRScKICAgICAgICBwcmludCgnRkFJTEVEX1NUQUdFPScrU1RBR0UpCiAgICAgICAgcHJpbnQoJ1NUT1A9JytyZWFzb24pCiAgICAgICAgc3lzLmV4aXQoMikK'
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
        self.assertEqual(r.IMAGES['v79-hub'],'sha256:d722f357206fec938eca691c92ddfe57ece62811f62124f6fbf760258b2b6940')
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
