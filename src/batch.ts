import { ApplePasswordManager } from "./client.ts";
import { Status } from "./const.ts";

interface Op {
  action: "new" | "set" | "change" | "rename" | "delete";
  url: string;
  username: string;
  password?: string;
  newUsername?: string;
}

interface Plan {
  ops: Op[];
}

interface RunOptions {
  planPath: string;
  dryRun: boolean;
  client: ApplePasswordManager;
}

export async function runBatch({ planPath, dryRun, client }: RunOptions) {
  const planText = await Deno.readTextFile(planPath);
  const plan: Plan = JSON.parse(planText);
  const total = plan.ops.length;
  console.error(`[batch] loaded ${total} ops from ${planPath}`);

  const logPath = `${planPath}.log`;
  const log = await Deno.open(logPath, {
    create: true,
    append: true,
    write: true,
  });
  const enc = new TextEncoder();
  const writeLog = async (s: string) => {
    await log.write(enc.encode(`${new Date().toISOString()} ${s}\n`));
  };
  await writeLog(`batch start total=${total} dryRun=${dryRun}`);

  let ok = 0;
  let fail = 0;
  for (let i = 0; i < plan.ops.length; i++) {
    const op = plan.ops[i];
    const tag = `[${i + 1}/${total}] ${op.action} ${op.url} ${op.username}`;
    if (dryRun) {
      console.error(`DRY ${tag}`);
      await writeLog(`DRY ${JSON.stringify(op)}`);
      continue;
    }
    try {
      let result: { STATUS?: Status } | unknown = null;
      switch (op.action) {
        case "new":
          result = await client.newAccount(op.url, op.username, op.password!);
          break;
        case "set":
          result = await client.setPassword(op.url, op.username, op.password!);
          break;
        case "change":
          result = await client.changePassword(
            op.url,
            op.username,
            op.password!,
          );
          break;
        case "rename":
          result = await client.renameAccount(
            op.url,
            op.username,
            op.newUsername!,
          );
          break;
        case "delete":
          result = await client.deleteAccount(op.url, op.username);
          break;
        default:
          throw new Error(`unknown action: ${op.action}`);
      }
      const status = (result as { STATUS?: Status })?.STATUS;
      if (status === Status.SUCCESS) {
        ok++;
        await writeLog(`OK ${JSON.stringify(op)} status=${status}`);
        if ((i + 1) % 10 === 0) {
          console.error(`progress: ${i + 1}/${total}  ok=${ok}  fail=${fail}`);
        }
      } else {
        fail++;
        await writeLog(`FAIL ${JSON.stringify(op)} status=${status}`);
        console.error(`FAIL ${tag}  status=${status}`);
      }
    } catch (e) {
      fail++;
      const msg = e instanceof Error ? e.message : String(e);
      await writeLog(`ERR ${JSON.stringify(op)} msg=${msg}`);
      console.error(`ERR ${tag}: ${msg}`);
    }
  }
  await writeLog(`batch end ok=${ok} fail=${fail}`);
  log.close();
  console.error(`[batch] done. ok=${ok} fail=${fail}. log: ${logPath}`);
  console.log(JSON.stringify({ total, ok, fail, log: logPath }));
}
