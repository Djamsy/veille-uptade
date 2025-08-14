import React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
export default function ProtectedRoute() {
  const { token, loading } = useAuth();
  const loc = useLocation();
  if (loading) return null;
  return token ? <Outlet/> : <Navigate to="/login" state={{ from: loc.pathname }} replace />;
}
