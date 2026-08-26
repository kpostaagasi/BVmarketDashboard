import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import type { Series } from "./types";
import * as yahoo from "./sources/yahoo";

const sources = [{ name: "yahoo", module: yahoo }];

const DATA_DIR = path.join(process.cwd(), "data");

async function writeSeries(series: Series): Promise<void> {
  const [kategori, ...rest] = series.id.split("/");
  if (!kategori || rest.length === 0 || rest.some((s) => !s)) {
    throw new Error(`Geçersiz seri id: "${series.id}" (beklenen: <kategori>/<ad>)`);
  }
  const dir = path.join(DATA_DIR, kategori);
  await mkdir(dir, { recursive: true });
  const file = path.join(dir, `${rest.join("-")}.json`);
  await writeFile(file, JSON.stringify(series, null, 2) + "\n", "utf8");
}

async function main(): Promise<number> {
  let failed = 0;
  for (const { name, module } of sources) {
    try {
      const seriesList = await module.ingest();
      for (const series of seriesList) {
        await writeSeries(series);
      }
      console.log(`[ok] ${name}: ${seriesList.length} seri`);
    } catch (e) {
      failed++;
      console.error(`[fail] ${name}: ${(e as Error).message}`);
    }
  }
  return failed > 0 ? 1 : 0;
}

main().then((code) => process.exit(code));
