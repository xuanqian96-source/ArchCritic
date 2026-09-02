// 新手指引状态：只在新账户注册完成后排队一次自动展示。
const ONBOARDING_PENDING_KEY = "archcritic_onboarding_pending";

// 标记新账户首次进入工作台时需要展示指引。
export function queueOnboardingTour() {
  sessionStorage.setItem(ONBOARDING_PENDING_KEY, "1");
}

// 消费一次自动展示标记，之后的普通登录不再自动出现。
export function consumeOnboardingTour() {
  if (sessionStorage.getItem(ONBOARDING_PENDING_KEY) !== "1") return false;
  sessionStorage.removeItem(ONBOARDING_PENDING_KEY);
  return true;
}
