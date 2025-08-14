import React, { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useNavigate, useLocation } from "react-router-dom";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const { state } = useLocation();
  const from = state?.from || "/";

  const [email,setEmail]=useState(""); const [password,setPassword]=useState("");
  const [err,setErr]=useState(""); const [loading,setLoading]=useState(false);

  async function onSubmit(e){ e.preventDefault(); setErr(""); setLoading(true);
    try { await login(email,password); nav(from,{replace:true}); }
    catch(e){ setErr(e.message||"Échec de connexion"); }
    finally{ setLoading(false); }
  }

  return (
    <form onSubmit={onSubmit} style={{maxWidth:420,margin:"60px auto"}}>
      <h1>Connexion</h1>
      <input type="email" required placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)} style={{width:"100%",padding:8,marginBottom:12}}/>
      <input type="password" required placeholder="Mot de passe" value={password} onChange={e=>setPassword(e.target.value)} style={{width:"100%",padding:8,marginBottom:12}}/>
      {err && <div style={{color:"red",marginBottom:12}}>{err}</div>}
      <button disabled={loading} style={{width:"100%",padding:10}}>{loading?"Connexion...":"Se connecter"}</button>
    </form>
  );
}
