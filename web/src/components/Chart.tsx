import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import { themeColors, useTheme } from "../theme";

echarts.use([LineChart, BarChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

export type ChartColors = ReturnType<typeof themeColors>;

/** Categorical colours of the series, checked for contrast on both themes. */
export const SERIES = ["#15803d", "#2563eb", "#d97706", "#7c3aed", "#dc2626", "#0891b2", "#db2777", "#65a30d"];

/** Axes, grid, legend and tooltip shared by every chart, in the colours of the current theme. */
export function baseOption(c: ChartColors): echarts.EChartsCoreOption {
  const axis = {
    axisLine: { lineStyle: { color: c.border } },
    axisTick: { show: false },
    axisLabel: { color: c.muted, fontSize: 11 },
    splitLine: { lineStyle: { color: c.border, type: "dashed" as const } },
    nameTextStyle: { color: c.muted, fontSize: 11 },
  };
  return {
    color: SERIES,
    animationDuration: 500,
    textStyle: { fontFamily: "Inter Variable, system-ui, sans-serif" },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, textStyle: { color: c.muted } },
    tooltip: {
      trigger: "axis",
      confine: true,
      backgroundColor: c.surface,
      borderColor: c.border,
      textStyle: { color: c.text, fontSize: 12 },
    },
    xAxis: { ...axis, splitLine: { show: false } },
    yAxis: axis,
  };
}

interface Props {
  /** Builds the chart from the theme colours; merged over `baseOption`. */
  option: (colors: ChartColors) => echarts.EChartsCoreOption;
  height?: number;
  label: string;
}

export function Chart({ option, height = 280, label }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const { theme } = useTheme();

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, null, { renderer: "canvas" });
    const colors = themeColors(theme);
    chart.setOption(baseOption(colors));
    chart.setOption(option(colors));
    const resize = new ResizeObserver(() => chart.resize());
    resize.observe(ref.current);
    return () => {
      resize.disconnect();
      chart.dispose();
    };
  }, [option, theme]);

  return <div ref={ref} style={{ height }} role="img" aria-label={label} />;
}
