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
test("Google login is server-configured and fails closed when unavailable; illustration remains local",()=>{
  const login=read("src/components/Login.tsx");
  const google=read("src/components/GoogleSignIn.tsx");
  const server=read("server.ts");
  assert.match(login,/<GoogleSignIn organizationId=\{organizationId\} onCredential=\{handleGoogleCredential\}/);
  assert.match(google,/config\?\.enabled !== true/);
  assert.match(google,/if \(status === "off"\) return null/);
  assert.match(google,/auto_select: false/);
  assert.match(google,/\/api\/auth\/google\/challenge/);
  assert.match(google,/You can still sign in with your password/);
  const route=server.slice(server.indexOf('app.post("/api/auth/google/login"'),server.indexOf('app.post("/api/auth/login"'));
  for(const marker of ["if(!hubGoogleLoginEnabled)", "sameOriginMutation(req)", "googleNonces.delete(nonce)", "verifyGoogleJwt(credential", "activeMembershipsForUser", "startLoginMfa(user", "completeHubLogin(user"]) assert.ok(route.includes(marker),marker);
  assert.ok(route.indexOf("googleNonces.delete(nonce)")<route.indexOf("verifyGoogleJwt(credential"));
  assert.ok(route.indexOf("startLoginMfa(user")<route.indexOf("completeHubLogin(user"));
  const expected=["/brand/icon-256.png",...["tiquet","ffpro","pos","marketing","academy"].map(x=>"/assets/login-products/"+x+".png")];
  for(const path of expected) {
    assert.ok(login.includes('src="'+path+'"'),path);
    const image=readFileSync(new URL("../public"+path,import.meta.url));
    assert.equal(image.subarray(0,8).toString("hex"),"89504e470d0a1a0a",path);
  }
  for(const match of login.matchAll(/<img\s+src="([^"]+)"/g)) assert.ok(match[1].startsWith("/"),match[1]);
});
test("reference CSS is explicitly scoped to the logged-out login surface",()=>{
  const css=read("src/index.css");
  assert.match(css,/\.hub-login-reference \.hub-login-network/);
  assert.match(css,/\.hub-login-reference \.hub-login-form/);
  assert.match(css,/@media \(max-width: 639px\)/);
});
