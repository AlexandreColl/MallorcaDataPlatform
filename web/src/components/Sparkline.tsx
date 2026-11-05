import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import { monthShort, number } from "../lib/format";

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

interface Props {
  points: { month: string; value: number }[];
  color: string;
  unit: string;
}

/** A small line of the last months with the value of each month on hover. */
export function Sparkline({ points, color, unit }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, null, { renderer: "canvas" });
    chart.setOption({
      animationDuration: 600,
      grid: { left: 0, right: 0, top: 4, bottom: 0 },
      xAxis: { type: "category", show: false, boundaryGap: false, data: points.map((p) => p.month) },
      yAxis: { type: "value", show: false, scale: true },
      tooltip: {
        trigger: "axis",
        confine: true,
        axisPointer: { type: "line", lineStyle: { color, opacity: 0.4 } },
        formatter: (params: { name: string; value: number }[]) => {
          const point = params[0];
          return point ? `${monthShort(point.name)} · <b>${number(point.value, 1)}</b> ${unit}` : "";
        },
      },
      series: [
        {
          type: "line",
          data: points.map((p) => p.value),
          smooth: 0.3,
          symbol: "none",
          lineStyle: { width: 2, color },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: `${color}55` },
              { offset: 1, color: `${color}00` },
            ]),
          },
        },
      ],
    });
    const resize = new ResizeObserver(() => chart.resize());
    resize.observe(ref.current);
    return () => {
      resize.disconnect();
      chart.dispose();
    };
  }, [points, color, unit]);

  return <div ref={ref} className="sparkline" role="img" aria-label="Evolución de los últimos meses" />;
}
