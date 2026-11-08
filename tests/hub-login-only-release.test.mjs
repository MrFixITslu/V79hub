import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = p => readFileSync(new URL("../"+p,import.meta.url),"utf8");
test("login presentation preserves all authentication and recovery routes",()=>{
  const login=read("src/components/Login.tsx");
  for(const url of ["/api/auth/login","/api/auth/mfa/complete-login","/api/auth/password-reset/request","/api/auth/password-reset/complete"]){
    assert.ok(login.includes(url),url);
  }
  for(const method of ["onSubmit={handleLogin}","onSubmit={completeMfa}","onSubmit={requestReset}","onSubmit={completeReset}"])assert.ok(login.includes(method),method);
});
test("Google login is server-gated and preserves existing MFA and local illustration",()=>{
  const login=read("src/components/Login.tsx");
  const google=read("src/components/GoogleSignIn.tsx");
  assert.match(login,/GoogleSignIn organizationId=/);
  assert.match(login,/\/api\/auth\/google\/login/);
  assert.match(login,/res\.status === 202 && data\.mfaRequired/);
  assert.match(login,/\/api\/auth\/mfa\/complete-login/);
  assert.match(google,/\/api\/auth\/google\/config/);
  assert.match(google,/config\?\.enabled !== true/);
  assert.match(google,/\/api\/auth\/google\/challenge/);
  assert.match(google,/auto_select: false/);
  assert.match(google,/Retry Google sign-in/);
  assert.doesNotMatch(google,/localStorage|sessionStorage/);
  assert.match(login,/\/assets\/v79-login-earth\.svg/);
  const image=read("public/assets/v79-login-earth.svg");
  assert.match(image,/<svg/);
  assert.match(image,/data:image\/webp;base64,/);
});
test("reference CSS is explicitly scoped to the logged-out login surface",()=>{
  const css=read("src/index.css");
  assert.match(css,/\.hub-login-reference \.hub-login-network/);
  assert.match(css,/\.hub-login-reference \.hub-login-form/);
  assert.match(css,/@media \(max-width: 639px\)/);
});
