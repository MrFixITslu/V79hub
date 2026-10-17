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
test("Google OAuth is clearly disabled; uploaded illustration is local and presentation-only",()=>{
  const login=read("src/components/Login.tsx");
  assert.match(login,/disabled aria-disabled="true"/);
  assert.match(login,/Google sign-in is not yet available/);
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
