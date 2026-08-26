"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Series } from "@/lib/types";

const trDate = (iso: string) =>
  new Date(iso).toLocaleDateString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  });

const trNumber = (value: number) =>
  value.toLocaleString("tr-TR", { maximumFractionDigits: 4 });

export default function ChartClient({ series }: { series: Series }) {
  const data = series.points.map((p) => ({ date: p.date, value: p.value }));

  return (
    <div className="h-80 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id={`fill-${series.id.replace("/", "-")}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={trDate}
            stroke="var(--muted)"
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            minTickGap={40}
          />
          <YAxis
            stroke="var(--muted)"
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={trNumber}
            width={64}
            domain={["auto", "auto"]}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              color: "var(--text)",
            }}
            labelStyle={{ color: "var(--muted)" }}
            formatter={(value) => [`${trNumber(Number(value))} ${series.unit}`, series.title]}
            labelFormatter={(label) => trDate(String(label))}
          />
          <Area
            type="monotone"
            dataKey="value"
            name={series.title}
            stroke="var(--accent)"
            strokeWidth={2}
            fill={`url(#fill-${series.id.replace("/", "-")})`}
            dot={false}
            activeDot={{ r: 4, fill: "var(--accent)" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
