"""Data analysis capability - statistics, aggregation, and insights."""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from typing import Any

from wish_granter.capabilities.base import Capability, CapabilityResult


class DataAnalysisCapability(Capability):
    name = "data_analysis"
    description = "Analyze data: statistics, aggregation, correlations, and insights"

    async def execute(self, params: dict[str, Any]) -> CapabilityResult:
        start = time.time()
        action = params.get("action", "describe")
        data = params.get("data", [])

        if not data and action != "insights":
            return self._result(False, error="No data provided", start_time=start)

        try:
            if action == "describe":
                result = self._describe(data)
            elif action == "correlate":
                result = self._correlate(data, params)
            elif action == "aggregate":
                result = self._aggregate(data, params)
            elif action == "filter":
                result = self._filter(data, params)
            elif action == "sort":
                result = self._sort(data, params)
            elif action == "frequency":
                result = self._frequency(data, params)
            elif action == "insights":
                result = self._insights(data, params)
            else:
                result = self._describe(data)

            return self._result(True, data=result, start_time=start)
        except Exception as e:
            return self._result(False, error=str(e), start_time=start)

    def _describe(self, data: list) -> dict[str, Any]:
        if not data:
            return {"error": "empty data"}

        if isinstance(data[0], dict):
            numeric_fields = {}
            categorical_fields = {}
            for key in data[0]:
                vals = [d.get(key) for d in data if d.get(key) is not None]
                try:
                    nums = [float(v) for v in vals]
                    numeric_fields[key] = {
                        "count": len(nums),
                        "mean": sum(nums) / len(nums) if nums else 0,
                        "min": min(nums) if nums else 0,
                        "max": max(nums) if nums else 0,
                        "std": self._std(nums) if len(nums) > 1 else 0,
                        "median": sorted(nums)[len(nums) // 2] if nums else 0,
                    }
                except (ValueError, TypeError):
                    counter = Counter(vals)
                    categorical_fields[key] = {
                        "count": len(vals),
                        "unique": len(counter),
                        "most_common": counter.most_common(5),
                    }
            return {"rows": len(data), "numeric": numeric_fields, "categorical": categorical_fields}
        else:
            try:
                nums = [float(v) for v in data]
                return {
                    "count": len(nums), "mean": sum(nums) / len(nums),
                    "min": min(nums), "max": max(nums),
                    "std": self._std(nums),
                    "median": sorted(nums)[len(nums) // 2],
                }
            except (ValueError, TypeError):
                counter = Counter(data)
                return {"count": len(data), "unique": len(counter), "most_common": counter.most_common(10)}

    def _correlate(self, data: list, params: dict) -> dict[str, Any]:
        field_x = params.get("field_x", "")
        field_y = params.get("field_y", "")
        method = params.get("method", "pearson")

        if not field_x or not field_y:
            return {"error": "field_x and field_y required"}

        pairs = [(d.get(field_x), d.get(field_y)) for d in data if d.get(field_x) is not None and d.get(field_y) is not None]
        try:
            x_vals = [float(p[0]) for p in pairs]
            y_vals = [float(p[1]) for p in pairs]
        except (ValueError, TypeError):
            return {"error": "Non-numeric values in specified fields"}

        n = len(x_vals)
        if n < 2:
            return {"error": "Need at least 2 data points"}

        mean_x = sum(x_vals) / n
        mean_y = sum(y_vals) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, y_vals)) / (n - 1)
        std_x = self._std(x_vals)
        std_y = self._std(y_vals)

        correlation = cov / (std_x * std_y) if std_x > 0 and std_y > 0 else 0

        return {"correlation": round(correlation, 6), "method": method, "n": n, "field_x": field_x, "field_y": field_y}

    def _aggregate(self, data: list, params: dict) -> dict[str, Any]:
        field = params.get("field", "")
        group_by = params.get("group_by", "")
        agg_fn = params.get("function", "sum")

        if not field:
            return {"error": "field required"}

        if group_by:
            groups: dict[str, list] = {}
            for d in data:
                key = str(d.get(group_by, "null"))
                groups.setdefault(key, []).append(d.get(field, 0))
            results = {}
            for key, vals in groups.items():
                nums = [float(v) for v in vals]
                results[key] = self._apply_agg(nums, agg_fn)
            return {"grouped": True, "field": field, "group_by": group_by, "results": results}
        else:
            nums = [float(d.get(field, 0)) for d in data]
            return {"grouped": False, "field": field, "result": self._apply_agg(nums, agg_fn)}

    def _filter(self, data: list, params: dict) -> dict[str, Any]:
        field = params.get("field", "")
        operator = params.get("operator", "eq")
        value = params.get("value")

        filtered = []
        for d in data:
            v = d.get(field)
            if operator == "eq" and v == value:
                filtered.append(d)
            elif operator == "ne" and v != value:
                filtered.append(d)
            elif operator == "gt" and v is not None and float(v) > float(value):
                filtered.append(d)
            elif operator == "lt" and v is not None and float(v) < float(value):
                filtered.append(d)
            elif operator == "gte" and v is not None and float(v) >= float(value):
                filtered.append(d)
            elif operator == "lte" and v is not None and float(v) <= float(value):
                filtered.append(d)
            elif operator == "contains" and v is not None and str(value).lower() in str(v).lower():
                filtered.append(d)

        return {"original_count": len(data), "filtered_count": len(filtered), "data": filtered}

    def _sort(self, data: list, params: dict) -> dict[str, Any]:
        field = params.get("field", "")
        reverse = params.get("reverse", False)
        try:
            sorted_data = sorted(data, key=lambda d: d.get(field, 0) if isinstance(d, dict) else d, reverse=reverse)
        except (TypeError, ValueError):
            sorted_data = sorted(data, key=lambda d: str(d.get(field, "")) if isinstance(d, dict) else str(d), reverse=reverse)
        return {"data": sorted_data, "sorted_by": field, "descending": reverse}

    def _frequency(self, data: list, params: dict) -> dict[str, Any]:
        field = params.get("field", "")
        if field and isinstance(data[0], dict):
            vals = [d.get(field) for d in data]
        else:
            vals = data
        counter = Counter(vals)
        return {"field": field, "frequency": dict(counter.most_common(50)), "unique_count": len(counter)}

    def _insights(self, data: list, params: dict) -> dict[str, Any]:
        insights = []
        if not data:
            return {"insights": ["Dataset is empty"]}

        if isinstance(data[0], dict):
            for key in data[0]:
                vals = [d.get(key) for d in data if d.get(key) is not None]
                try:
                    nums = [float(v) for v in vals]
                    mean = sum(nums) / len(nums)
                    std = self._std(nums)
                    outliers = [v for v in nums if abs(v - mean) > 2 * std] if std > 0 else []
                    if outliers:
                        insights.append(f"{key}: {len(outliers)} outlier(s) detected (>{2*std:.2f} from mean)")
                    if std / mean > 0.5 if mean != 0 else False:
                        insights.append(f"{key}: High variability (CV={std/mean:.2f})")
                except (ValueError, TypeError):
                    counter = Counter(vals)
                    top = counter.most_common(1)[0]
                    concentration = top[1] / len(vals) * 100
                    if concentration > 50:
                        insights.append(f"{key}: Dominant value '{top[0]}' ({concentration:.0f}% of data)")

        return {"insights": insights, "data_points": len(data)}

    @staticmethod
    def _std(vals: list[float]) -> float:
        if len(vals) < 2:
            return 0.0
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
        return math.sqrt(variance)

    @staticmethod
    def _apply_agg(nums: list[float], fn: str) -> float:
        if not nums:
            return 0
        if fn == "sum":
            return sum(nums)
        elif fn == "mean":
            return sum(nums) / len(nums)
        elif fn == "median":
            s = sorted(nums)
            return s[len(s) // 2]
        elif fn == "min":
            return min(nums)
        elif fn == "max":
            return max(nums)
        elif fn == "count":
            return len(nums)
        elif fn == "std":
            n = len(nums)
            mean = sum(nums) / n
            return math.sqrt(sum((x - mean) ** 2 for x in nums) / (n - 1)) if n > 1 else 0
        return sum(nums)