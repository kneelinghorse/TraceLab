import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

async function accessible(page: Page) {
  await page.addScriptTag({path:path.resolve("node_modules/axe-core/axe.min.js")});
  const result = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node:Document) => Promise<{violations:{id:string;impact:string}[]}> } }).axe;
    return { overflow: document.documentElement.scrollWidth > innerWidth, violations:(await axe.run(document)).violations.filter(v => ["critical","serious"].includes(v.impact)) };
  });
  expect(result).toEqual({overflow:false, violations:[]});
}
for (const theme of ["light","dark"] as const) for (const width of [390,1440]) {
  test("shared confirmations and collection forms are accessible in "+theme+" at "+width, async ({page}) => {
    const writes:string[]=[];
    await page.setViewportSize({width,height:1000});
    await page.emulateMedia({colorScheme:theme});
    await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2",JSON.stringify({token:"fixture",user_id:"operator",email:"operator@example.test",display_name:"Operator"})));
    await page.route("**/api/v1/**",async route => {
      const pathname=new URL(route.request().url()).pathname;
      if (route.request().method()!=="GET") writes.push(pathname);
      let body:unknown={};
      const collection={id:"collection",name:"Auditable research",description:"Preserve original sources",created_at:"2026-09-13T00:00:00Z",updated_at:"2026-09-13T00:00:00Z",item_count:1,items:[{id:"item",collection_id:"collection",chunk_id:"chunk",notes:null,added_at:"2026-09-13T00:00:00Z",chunk_content:"Original research finding",document_id:"doc"}]};
      if(pathname.endsWith("/auth/me"))body={user_id:"operator",email:"operator@example.test",display_name:"Operator",role:"admin"};
      else if(pathname.endsWith("/admin/users"))body=[{id:"member",email:"member@example.test",display_name:"Member",role:"member",is_active:true,created_at:"2026-09-13T00:00:00Z",last_login_at:null}];
      else if(pathname.endsWith("/collections/collection/documents"))body={items:[],total:0,page:1,page_size:20};
      else if(pathname.endsWith("/collections/collection"))body=collection;
      else if(pathname.endsWith("/collections"))body={data:[collection],total:1};
      else if(pathname.endsWith("/documents"))body={data:[{id:"doc",name:"Source document",project_id:"project",file_type:"txt",processed:true,chunked:false,embedded:false}],pagination:{page:1,pages:1,total:1}};
      else if(pathname.endsWith("/projects"))body={data:[{id:"project",name:"Research project"}],pagination:{page:1,pages:1,total:1}};
      await route.fulfill({json:body});
    });
    await page.goto("/documents");
    const remove=page.getByRole("button",{name:"Delete Source document",exact:true});
    await remove.click();
    const dialog=page.getByRole("dialog",{name:"Confirm action"});
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button",{name:"Cancel",exact:true})).toBeFocused();
    for (let i=0;i<8;i++) {
      await page.keyboard.press(i<4?"Tab":"Shift+Tab");
      expect(await dialog.evaluate(el=>el.contains(document.activeElement))).toBe(true);
    }
    await accessible(page);
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(remove).toBeFocused();
    await page.goto("/collections");
    await page.getByRole("button",{name:"New Collection",exact:true}).click();
    await page.getByLabel("Collection name",{exact:true}).fill("Unsaved collection");
    await accessible(page);
    await page.getByRole("button",{name:"Cancel",exact:true}).click();
    await page.goto("/collections/collection");
    await page.getByRole("button",{name:"Edit",exact:true}).click();
    await expect(page.getByLabel("Collection name",{exact:true})).toHaveValue("Auditable research");
    await accessible(page);
    await page.getByRole("button",{name:"Cancel",exact:true}).click();
    const createReport=page.getByRole("button",{name:"Create Report",exact:true});
    await createReport.click();
    const report=page.getByRole("dialog",{name:"Create Report",exact:true});
    await expect(report).toBeVisible();
    await accessible(page);
    await page.keyboard.press("Escape");
    await expect(report).not.toBeVisible();
    await expect(createReport).toBeFocused();
    await page.goto("/admin/users");
    const deleteUser=page.getByRole("button",{name:"Delete",exact:true});
    await deleteUser.click();
    const userDialog=page.getByRole("dialog",{name:"Delete member@example.test?",exact:true});
    await expect(userDialog).toBeVisible();
    await expect(userDialog.getByRole("button",{name:"Cancel",exact:true})).toBeFocused();
    for (let i=0;i<6;i++) {
      await page.keyboard.press(i<3?"Tab":"Shift+Tab");
      expect(await userDialog.evaluate(el=>el.contains(document.activeElement))).toBe(true);
    }
    await accessible(page);
    await page.keyboard.press("Escape");
    await expect(userDialog).not.toBeVisible();
    await expect(deleteUser).toBeFocused();
    expect(writes).toEqual([]);
  });
}
