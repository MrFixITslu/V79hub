import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {chromium} from "playwright";
import fs from "node:fs";

const browser = await chromium.launch({headless:true,args:["--no-sandbox"]});
fs.mkdirSync("preview-artifacts/skill-manager",{recursive:true});
try {
  for(const [label,viewport] of [["desktop",{width:1380,height:900}],["mobile",{width:390,height:844}]]) {
    const page = await browser.newPage({viewport});
    const clientErrors=[];
    page.on("pageerror",e=>clientErrors.push(e.message));
    const original="# Website security\nCreate a clean accessible law firm website. Review against OWASP and WCAG.";
    const sha=createHash("sha256").update(original).digest("hex");
    const builtins=[
      {id:"ceo",name:"CEO",focus:"Leadership review",skillSha:"synthetic-ceo",bytes:39,protected:true},
      {id:"coo",name:"COO",focus:"Service delivery",skillSha:"synthetic-coo",bytes:39,protected:true},
      {id:"finance",name:"Finance",focus:"Budget review",skillSha:"synthetic-finance",bytes:39,protected:true},
      {id:"strategy",name:"Strategy",focus:"Portfolio review",skillSha:"synthetic-strategy",bytes:39,protected:true},
      {id:"marketing",name:"Marketing",focus:"Campaign review",skillSha:"synthetic-marketing",bytes:39,protected:true},
      {id:"customer-service",name:"Customer Service",focus:"Support review",skillSha:"synthetic-customer",bytes:39,protected:true},
      {id:"technical-security",name:"Technical & Security",focus:"Technical review",skillSha:"synthetic-tech",bytes:39,protected:true},
      {id:"sales",name:"Sales",focus:"Sales review",skillSha:"synthetic-sales",bytes:39,protected:true},
    ];
    let record=null, activates=0;
    await page.route("**/api/**",async route=>{
      const u=new URL(route.request().url()),p=u.pathname.replace(/\/$/, ""),m=route.request().method();
      const json=(body,status=200)=>route.fulfill({status,contentType:"application/json",body:JSON.stringify(body)});
      if(p==="/api/auth/me")return json({user:{
        id:"synthetic-owner",username:"test",fullName:"Synthetic Owner",role:"admin",
        platformOperator:true,ownerAgent:true,workspaceOwner:true,
        permissions:["overview","team","security","billing","assistant","admin"]
      },organization:{name:"Synthetic Review Workspace"}});
      if(p==="/api/ecosystem/apps"||p==="/api/users")return json([]);
      if(p==="/api/agent/skills" && m==="GET")return json({skills:record?[{
        id:record.id,name:record.name,revision:record.revision,activeVersion:record.activeVersion,
        latestVersion:record.latestVersion,workers:record.workers,status:record.status,updatedAt:record.updatedAt
      }]:[],audit:[],limits:{maxContentBytes:6000,maxPerWorker:2}});
      if(p==="/api/agent/skills/builtins" && m==="GET")return json({skills:builtins});
      if(p.startsWith("/api/agent/skills/builtins/") && m==="GET"){
        const id=p.split("/").at(-1),role=builtins.find(x=>x.id===id);
        return role?json({skill:{...role,content:"# Original safe role guidance for "+role.name}}):json({error:"Unknown role"},404);
      }
      if(p==="/api/agent/skills/validate" && m==="POST")return json({name:"Law Firm Website",bytes:Buffer.byteLength(original),sha256:sha,warnings:[],
        result:"format-only",note:"Synthetic browser test only"});
      if(p==="/api/agent/skills" && m==="POST"){
        const data=route.request().postDataJSON();
        assert.equal(data.content,original);
        record={id:"skill-1111111111111111",name:data.name,revision:1,latestVersion:1,
          activeVersion:null,workers:[],status:"draft",updatedAt:"2026-11-01T12:00:00Z",
          versions:[{version:1,name:data.name,content:data.content,sha256:sha,createdAt:"2026-11-01T12:00:00Z"}]};
        return json({skill:record},201);
      }
      if(record && p==="/api/agent/skills/"+record.id && m==="GET")return json(record);
      if(record && p.endsWith("/activate")&&m==="POST") {
        const data=route.request().postDataJSON();
        assert.equal(data.expectedRevision,1);
        assert.equal(data.version,1);
        assert.deepEqual(data.workers,["technical-security"]);
        record.revision=2;record.activeVersion=1;record.workers=data.workers;record.status="active";activates++;
        return json({skill:record});
      }
      if(record && p.endsWith("/pause") && m==="POST"){
        record.revision++;record.workers=[];record.status="paused";return json({skill:record});
      }
      return json({error:"Synthetic unknown endpoint"},404);
    });
    await page.goto("http://127.0.0.1:4178/?view=assistant",{waitUntil:"domcontentloaded"});
    await page.getByRole("button",{name:"Skill Library"}).click();
    await page.getByRole("heading",{name:"Skill Library"}).waitFor();
    await page.getByText("Protected built-in skills (8)").waitFor();
    await page.getByRole("button",{name:/Technical & Security Verified original/}).click();
    await page.getByRole("textbox",{name:"Protected Technical & Security instructions"}).waitFor();
    await page.getByRole("button",{name:"Improve this skill"}).click();
    await page.getByRole("textbox",{name:"Skill instructions"}).waitFor();
    assert.match(await page.getByRole("textbox",{name:"Skill name"}).inputValue(),/Technical & Security/);
    await page.getByRole("button",{name:"New skill"}).click();
    await page.getByRole("textbox",{name:"Skill name"}).fill("Law Firm Website");
    await page.getByRole("textbox",{name:"Skill instructions"}).fill(original);
    await page.getByRole("button",{name:"Check draft"}).click();
    await page.getByText("Format check:").waitFor();
    await page.getByRole("button",{name:"Save draft"}).click();
    await page.getByRole("heading",{name:"Assign to workers"}).waitFor();
    await page.getByRole("checkbox",{name:"Technical & Security"}).check();
    await page.getByRole("button",{name:"Check draft"}).click();
    await page.getByRole("checkbox",{name:/I reviewed the instructions/}).check();
    await page.getByRole("button",{name:"Activate exact version"}).click();
    await page.getByText(/Worker assignment activated/).waitFor();
    assert.equal(activates,1);
    assert.equal(record.status,"active");
    await page.screenshot({path:"preview-artifacts/skill-manager/"+label+".png",fullPage:true});
    assert.deepEqual(clientErrors,[]);
    console.log("SKILL_MANAGER_BROWSER_"+label.toUpperCase()+"=PASS");
    await page.close();
  }
}finally{await browser.close();}
