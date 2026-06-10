import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function AuthPage() {
  const { login, register, username, logout } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ username: "", password: "" });
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setLoading(true);
      setMessage("");
      if (mode === "login") {
        await login(form.username, form.password);
      } else {
        await register(form.username, form.password);
      }
      navigate("/");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "认证失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }

  if (username) {
    return (
      <section className="mx-auto max-w-xl rounded-lg border border-white/10 bg-white/[0.06] p-6">
        <h1 className="text-2xl font-semibold">已登录</h1>
        <p className="mt-3 text-paper/65">当前账号：{username}</p>
        <button onClick={logout} className="mt-5 rounded-lg border border-white/15 px-4 py-3 text-paper hover:bg-white/10">
          退出登录
        </button>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-xl rounded-lg border border-white/10 bg-white/[0.06] p-6 shadow-soft">
      <p className="text-sm font-medium text-gold">虚拟资金模拟游戏</p>
      <h1 className="mt-1 text-2xl font-semibold">{mode === "login" ? "登录" : "注册"}账号</h1>
      <div className="mt-5 grid grid-cols-2 rounded-lg bg-pitch p-1">
        <button type="button" onClick={() => setMode("login")} className={`rounded-md py-2 text-sm ${mode === "login" ? "bg-gold text-pitch" : "text-paper/65"}`}>
          登录
        </button>
        <button type="button" onClick={() => setMode("register")} className={`rounded-md py-2 text-sm ${mode === "register" ? "bg-gold text-pitch" : "text-paper/65"}`}>
          注册
        </button>
      </div>
      <form onSubmit={submit} className="mt-5 space-y-4">
        <label className="block text-sm text-paper/65">
          用户名
          <input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} className="mt-2 w-full rounded-lg border border-white/10 bg-pitch px-3 py-3 text-paper" required minLength={3} />
        </label>
        <label className="block text-sm text-paper/65">
          密码
          <input value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} className="mt-2 w-full rounded-lg border border-white/10 bg-pitch px-3 py-3 text-paper" type="password" required minLength={8} />
        </label>
        <button disabled={loading} className="w-full rounded-lg bg-gold px-4 py-3 font-semibold text-pitch disabled:opacity-60">
          {loading ? "处理中" : mode === "login" ? "登录模拟账号" : "注册模拟账号"}
        </button>
      </form>
      {message ? <div className="mt-4 rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm">{message}</div> : null}
    </section>
  );
}
