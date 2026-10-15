import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Page from "./components/Page.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import Landing from "./pages/Landing.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import NotFound from "./pages/NotFound.jsx";
import Apply from "./pages/Apply.jsx";
import MyApplications from "./pages/applicant/MyApplications.jsx";
import ApplicantApplicationDetail from "./pages/applicant/ApplicationDetail.jsx";
import StaffDashboard from "./pages/staff/StaffDashboard.jsx";
import StaffApplications from "./pages/staff/StaffApplications.jsx";
import StaffApplicationDetail from "./pages/staff/StaffApplicationDetail.jsx";
import ModelInsights from "./pages/staff/ModelInsights.jsx";
import { STAFF_ROLES } from "./lib/auth.jsx";

const staff = (element, roles = STAFF_ROLES) => (
  <ProtectedRoute roles={roles}><Page>{element}</Page></ProtectedRoute>
);

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/apply" element={
          <ProtectedRoute roles={["applicant"]}><Apply /></ProtectedRoute>
        } />
        <Route path="/dashboard" element={
          <ProtectedRoute roles={["applicant"]}><Page><MyApplications /></Page></ProtectedRoute>
        } />
        <Route path="/dashboard/applications/:id" element={
          <ProtectedRoute roles={["applicant"]}><Page><ApplicantApplicationDetail /></Page></ProtectedRoute>
        } />
        <Route path="/staff" element={staff(<StaffDashboard />)} />
        <Route path="/staff/applications" element={staff(<StaffApplications />)} />
        <Route path="/staff/applications/:id" element={staff(<StaffApplicationDetail />)} />
        <Route path="/staff/models" element={staff(<ModelInsights />, ["credit_analyst"])} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
