/** 与 football-betting-common password_policy 一致 */

const HINT =
  '至少 8 位，须含英文字母、数字和符号（如 ! # $ - _），不能含空格';

function validatePasswordClient(pw) {
  const p = (pw || '').trim();
  if (!p) return '请输入密码';
  if (/\s/.test(p)) return '密码不能包含空格';
  if (p.length < 8) return '密码至少 8 位';
  if (!/[A-Za-z]/.test(p)) return '密码须包含英文字母';
  if (!/\d/.test(p)) return '密码须包含数字';
  if (!/[!@#$%^&*()_+\-=[\]{}|;:,.<>?/~`'"']/.test(p)) return '密码须包含符号';
  return '';
}

module.exports = {
  PASSWORD_POLICY_HINT: HINT,
  validatePasswordClient,
};
