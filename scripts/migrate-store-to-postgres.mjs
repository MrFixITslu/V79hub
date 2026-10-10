import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { Pool } from "pg";
import { PostgresStoreRepository, migrateJsonState } from "../server/postgres-store.mjs";

const dataDir = path.resolve(process.env.DATA_DIR || path.join(process.cwd(), "data"));
const storeFile = path.resolve(process.env.V79_HUB_STORE_FILE || path.join(dataDir, "v79_store.json"));
const databaseUrl = String(process.env.DATABASE_URL || "").trim();

if (!databaseUrl) {
  console.error("DATABASE_URL is required.");
  process.exit(2);
}
if (!fs.existsSync(storeFile)) {
  console.error(`Hub JSON migration source not found: ${storeFile}`);
  process.exit(2);
}

let source;
try {
  source = JSON.parse(fs.readFileSync(storeFile, "utf8"));
} catch (error) {
  console.error("Unable to read the Hub JSON migration source:", error instanceof Error ? error.message : error);
  process.exit(2);
}
const pool = new Pool({
  connectionString: databaseUrl,
  max: 2,
  connectionTimeoutMillis: 5000,
  idleTimeoutMillis: 5000,
});

try {
  const repository = new PostgresStoreRepository(pool);
  const migrated = await migrateJsonState(repository, source);
  if (!migrated.imported) {
    console.log(`PostgreSQL Hub state already exists at revision ${migrated.current.revision}; JSON was not imported.`);
    process.exitCode = 3;
  } else {
    console.log(`Imported Hub JSON state into PostgreSQL at revision ${migrated.current.revision}.`);
    console.log("The JSON source was preserved and must be retained as a migration backup until cutover is verified.");
  }
} catch (error) {
  console.error("Hub PostgreSQL migration failed:", error instanceof Error ? error.message : error);
  process.exitCode = 1;
} finally {
  await pool.end();
}
