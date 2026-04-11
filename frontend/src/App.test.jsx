/* 验证前端页面可以提交信息并展示评图结果。 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import App from "./App";

const mockFetch = vi.fn();

vi.stubGlobal("fetch", mockFetch);

describe("App", () => {
  test("提交演示内容后显示评图结果", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: "ok", service: "archcritic" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 1, name: "演示项目" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 2 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          overall_score: 82,
          grade: "B",
          summary: "测试评图摘要",
          must_fix: ["需要补充功能分区依据。"],
          should_improve: ["建议加强流线表达。"],
          optional_improvements: ["可补充材料意向。"],
          strengths: ["项目主题清晰。"],
          agent_evaluations: [
            {
              agent_type: "site_agent",
              dimension: "场地与回应",
              score: 80,
              summary: "测试维度摘要",
              strengths: ["场地关系基本明确。"],
              issues: ["仍缺少更具体分析。"],
              suggestions: ["补充入口与环境图。"]
            }
          ],
        }),
      });

    render(<App />);

    fireEvent.change(screen.getByLabelText("项目名称"), {
      target: { value: "演示项目" },
    });
    fireEvent.change(screen.getByLabelText("建筑类型"), {
      target: { value: "公共建筑" },
    });
    fireEvent.change(screen.getByLabelText("提交人"), {
      target: { value: "学生甲" },
    });
    fireEvent.change(screen.getByLabelText("设计说明"), {
      target: { value: "一个用于前端验证的演示方案。" },
    });

    fireEvent.click(screen.getByRole("button", { name: "生成演示评图" }));

    await waitFor(() => {
      expect(screen.getByText("测试评图摘要")).toBeInTheDocument();
    });

    expect(screen.getByText("82")).toBeInTheDocument();
    expect(screen.getByText("场地与回应")).toBeInTheDocument();
  });
});
