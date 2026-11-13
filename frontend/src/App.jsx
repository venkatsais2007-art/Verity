import { Routes, Route } from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import KnowledgeBase from "./pages/KnowledgeBase";
import NewSubmission from "./pages/NewSubmission";
import SubmissionDetail from "./pages/SubmissionDetail";
import Insights from "./pages/insights";
import ProtectedRoute from "./components/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/knowledge"
             element={<ProtectedRoute roles={["admin"]}><KnowledgeBase /></ProtectedRoute>} />
      <Route path="/insights"
             element={<ProtectedRoute roles={["admin", "manager", "reviewer"]}><Insights /></ProtectedRoute>} />
      <Route path="/submissions/new"
             element={<ProtectedRoute roles={["creator"]}><NewSubmission /></ProtectedRoute>} />
      <Route path="/submissions/:id"
             element={<ProtectedRoute><SubmissionDetail /></ProtectedRoute>} />
    </Routes>
  );
}
