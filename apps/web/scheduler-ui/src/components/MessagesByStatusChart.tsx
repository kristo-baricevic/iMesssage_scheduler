import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

type StatusDatum = {
  status: string;
  count: number;
};

const fills = [
  "#B8B8FF",
  "#8A8AFF",
  "#5C5CFF",
  "#2E2EFF",
  "#0000FF",
  "#0000D1",
  "#0000A3",
];

export function MessagesByStatusChart({ data }: { data: StatusDatum[] }) {
  return (
    <div className="w-full h-65 rounded-xl border bg-slate-100 p-4 shadow-xl">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">
        Messages by Status
      </h3>

      <ResponsiveContainer width="90%" height="85%">
        <BarChart data={data}>
          <XAxis dataKey="status" />
          <YAxis allowDecimals={false} />
          <Tooltip
            contentStyle={{ color: "#94a3b8" }}
            labelStyle={{ color: "#94a3b8" }}
            itemStyle={{ color: "#94a3b8" }}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {fills.map((fill, i) => (
              <Cell key={i} fill={fill} />
            ))}
          </Bar>{" "}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
