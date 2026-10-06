import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Archive, BookOpen, ChevronDown, ChevronRight, Copy, FileText,
  GraduationCap, Layers3, Loader2, Plus, RefreshCw, Save,
  Search, Send, Settings2, Trash2, X, Users, CreditCard, ShieldCheck,
} from "lucide-react";
import { EcosystemApp } from "../types";
import { academyAdminApi } from "../lib/academyAdmin";
import { AcademyLearners } from "./AcademyLearners";
import { AcademyPublishing } from "./AcademyPublishing";
import { AcademyImport } from "./AcademyImport";
import { AcademyJuniorAdmin } from "./AcademyJuniorAdmin";
import { TiquetPlatformAdmin } from "./TiquetPlatformAdmin";
import { MarketingPlatformAdmin } from "./MarketingPlatformAdmin";
import { POSPlatformAdmin } from "./POSPlatformAdmin";
import { FFPROPlatformAdmin } from "./FFPROPlatformAdmin";
import { PlatformAdminOverview } from "./PlatformAdminOverview";
import { PlatformCustomersAdmin } from "./PlatformCustomersAdmin";
import { PlatformPlansAdmin } from "./PlatformPlansAdmin";
import { PlatformAuditAdmin } from "./PlatformAuditAdmin";

type CourseStatus = "Draft" | "Review" | "Ready for Upload" | "Uploaded" | "Imported" | "Published" | "Archived";
type PricingType = "free" | "free_trial" | "premium" | "subscription";

interface Course {
  id: string;
  title: string;
  shortDescription?: string;
  fullDescription?: string;
  category?: string;
  difficultyLevel?: string;
  instructor?: string;
  courseVersion?: string;
  thumbnail?: string;
  estimatedDuration?: string;
  prerequisites?: string[];
  learningObjectives?: string[];
  status: CourseStatus;
  pricingType: PricingType;
  price: number;
  moduleCount?: number;
  lessonCount?: number;
  websiteAppId?: number;
  updatedAt?: string;
}

interface Module {
  id: string;
  courseId: string;
  title: string;
  description?: string;
  orderNumber: number;
}

interface Lesson {
  id: string;
  moduleId: string;
  courseId: string;
  title: string;
  description?: string;
  learningObjectives?: string[];
  estimatedTime?: string;
  lessonContent?: string;
  videoUrl?: string;
  audioUrl?: string;
  exercisePrompt?: string;
  orderNumber: number;
}

interface QuizQuestion {
  id: string;
  questionText: string;
  questionType: "multiple_choice" | "true_false";
  options: string[];
  correctAnswer: string | number;
  explanation: string;
  orderNumber: number;
}

interface Quiz {
  id: string;
  lessonId: string;
  title: string;
  passingScore: number;
  questions: QuizQuestion[];
}

interface AdminConsoleProps {
  ecosystemApps: EcosystemApp[];
}

type AdminSection = "academy" | "platform";
type PlatformView = "overview" | "customers" | "applications" | "plans" | "audit";
type PlatformProductView = "pos" | "ffpro" | "tiquet" | "marketing";
type AcademyView = "courses" | "learners" | "publishing" | "import" | "junior";
const emptyCourse = (): Partial<Course> => ({
  title: "",
  shortDescription: "",
  fullDescription: "",
  category: "General",
  difficultyLevel: "Beginner",
  instructor: "V79 Academy Instructor",
  courseVersion: "1.0.0",
  estimatedDuration: "2.0 hours",
  prerequisites: [],
  learningObjectives: [],
  status: "Draft",
  pricingType: "free",
  price: 0,
});

const statusClass: Record<string, string> = {
  Published: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Uploaded: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Draft: "bg-slate-100 text-slate-600 border-slate-200",
  Review: "bg-amber-50 text-amber-700 border-amber-200",
  Imported: "bg-cyan-50 text-cyan-700 border-cyan-200",
  Archived: "bg-rose-50 text-rose-700 border-rose-200",
};

export function AdminConsole({ ecosystemApps }: AdminConsoleProps) {
  const [section, setSection] = useState<AdminSection>("platform");
  const [academyView, setAcademyView] = useState<AcademyView>("courses");
  const [platformView, setPlatformView] = useState<PlatformView>("overview");
  const [platformProductView, setPlatformProductView] = useState<PlatformProductView>("pos");
  const [courses, setCourses] = useState<Course[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Partial<Course> | null>(null);
  const [modules, setModules] = useState<Module[]>([]);
  const [lessonsByModule, setLessonsByModule] = useState<Record<string, Lesson[]>>({});
  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const flash = (text: string, type: "success" | "error" = "success") => {
    setMessage({ text, type });
    window.setTimeout(() => setMessage(null), 5000);
  };

  const loadCourses = useCallback(async () => {
    setLoading(true);
    try {
      const data = await academyAdminApi<Course[]>("/courses");
      setCourses(data);
      if (selectedId) {
        const current = data.find((course) => course.id === selectedId);
        if (current) setDraft(current);
      }
    } catch (error) {
      flash(error instanceof Error ? error.message : "Could not load Academy courses", "error");
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    if (section === "academy") void loadCourses();
  }, [section]);

  const selectCourse = async (course: Course) => {
    setSelectedId(course.id);
    setDraft(course);
    setModules([]);
    setLessonsByModule({});
    setExpandedModules(new Set());
    try {
      setModules(await academyAdminApi<Module[]>(`/courses/${course.id}/modules`));
    } catch (error) {
      flash(error instanceof Error ? error.message : "Could not load course modules", "error");
    }
  };

  const startNewCourse = () => {
    setSelectedId(null);
    setDraft(emptyCourse());
    setModules([]);
    setLessonsByModule({});
    setExpandedModules(new Set());
  };

  const saveCourse = async () => {
    if (!draft?.title?.trim()) return flash("A course title is required.", "error");
    setBusy(true);
    try {
      const payload = {
        ...draft,
        prerequisites: draft.prerequisites || [],
        learningObjectives: draft.learningObjectives || [],
        price: ["subscription", "premium"].includes(draft.pricingType || "free") ? Number(draft.price || 0) : 0,
      };
      const wasExisting = Boolean(selectedId);
      const saved = selectedId
        ? await academyAdminApi<Course>(`/courses/${selectedId}`, { method: "PUT", body: JSON.stringify(payload) })
        : await academyAdminApi<Course>("/courses", { method: "POST", body: JSON.stringify(payload) });
      setSelectedId(saved.id);
      setDraft(saved);
      await loadCourses();
      flash(wasExisting ? "Course changes saved." : "Course created.");
    } catch (error) {
      flash(error instanceof Error ? error.message : "Course could not be saved", "error");
    } finally {
      setBusy(false);
    }
  };

  const publishCourse = async () => {
    if (!selectedId) return;
    setBusy(true);
    try {
      const result = await academyAdminApi<{ course: Course }>(`/courses/${selectedId}/publish`, {
        method: "POST",
        body: JSON.stringify({ userRole: "Admin" }),
      });
      setDraft(result.course);
      await loadCourses();
      flash("Course published successfully.");
    } catch (error) {
      flash(error instanceof Error ? error.message : "Course could not be published", "error");
    } finally {
      setBusy(false);
    }
  };

  const duplicateCourse = async () => {
    if (!selectedId) return;
    setBusy(true);
    try {
      const copy = await academyAdminApi<Course>(`/courses/${selectedId}/duplicate`, { method: "POST" });
      await loadCourses();
      await selectCourse(copy);
      flash("Course duplicated.");
    } catch (error) {
      flash(error instanceof Error ? error.message : "Course could not be duplicated", "error");
    } finally {
      setBusy(false);
    }
  };

  const archiveCourse = async () => {
    if (!selectedId || !draft) return;
    setBusy(true);
    try {
      const saved = await academyAdminApi<Course>(`/courses/${selectedId}`, {
        method: "PUT",
        body: JSON.stringify({ ...draft, status: "Archived", userRole: "Admin" }),
      });
      setDraft(saved);
      await loadCourses();
      flash("Course archived.");
    } catch (error) {
      flash(error instanceof Error ? error.message : "Course could not be archived", "error");
    } finally {
      setBusy(false);
    }
  };

  const deleteCourse = async () => {
    if (!selectedId || !draft) return;
    if (!window.confirm(`Delete "${draft.title}" and all associated course content? This cannot be undone.`)) return;
    setBusy(true);
    try {
      await academyAdminApi(`/courses/${selectedId}`, { method: "DELETE" });
      setSelectedId(null);
      setDraft(null);
      setModules([]);
      await loadCourses();
      flash("Course deleted.");
    } catch (error) {
      flash(error instanceof Error ? error.message : "Course could not be deleted", "error");
    } finally {
      setBusy(false);
    }
  };

  const addModule = async () => {
    if (!selectedId) return;
    try {
      const row = await academyAdminApi<Module>(`/courses/${selectedId}/modules`, {
        method: "POST",
        body: JSON.stringify({ title: "New Module", description: "" }),
      });
      setModules((current) => [...current, row]);
      flash("Module added.");
    } catch (error) {
      flash(error instanceof Error ? error.message : "Module could not be added", "error");
    }
  };

  const updateModule = async (module: Module, patch: Partial<Module>) => {
    try {
      const updated = await academyAdminApi<Module>(`/modules/${module.id}`, {
        method: "PUT",
        body: JSON.stringify(patch),
      });
      setModules((current) => current.map((row) => row.id === updated.id ? updated : row));
    } catch (error) {
      flash(error instanceof Error ? error.message : "Module could not be saved", "error");
    }
  };

  const deleteModule = async (module: Module) => {
    if (!window.confirm(`Delete module "${module.title}" and all of its lessons?`)) return;
    try {
      await academyAdminApi(`/modules/${module.id}`, { method: "DELETE" });
      setModules((current) => current.filter((row) => row.id !== module.id));
      setLessonsByModule((current) => {
        const next = { ...current };
        delete next[module.id];
        return next;
      });
      flash("Module deleted.");
    } catch (error) {
      flash(error instanceof Error ? error.message : "Module could not be deleted", "error");
    }
  };

  const toggleModule = async (module: Module) => {
    const next = new Set(expandedModules);
    if (next.has(module.id)) {
      next.delete(module.id);
      setExpandedModules(next);
      return;
    }
    next.add(module.id);
    setExpandedModules(next);
    if (!lessonsByModule[module.id]) {
      try {
        const lessons = await academyAdminApi<Lesson[]>(`/modules/${module.id}/lessons`);
        setLessonsByModule((current) => ({ ...current, [module.id]: lessons }));
      } catch (error) {
        flash(error instanceof Error ? error.message : "Lessons could not be loaded", "error");
      }
    }
  };

  const addLesson = async (module: Module) => {
    try {
      const lesson = await academyAdminApi<Lesson>(`/modules/${module.id}/lessons`, {
        method: "POST",
        body: JSON.stringify({ title: "New Lesson", estimatedTime: "20 mins" }),
      });
      setLessonsByModule((current) => ({
        ...current,
        [module.id]: [...(current[module.id] || []), lesson],
      }));
      setExpandedModules((current) => new Set(current).add(module.id));
      flash("Lesson added.");
    } catch (error) {
      flash(error instanceof Error ? error.message : "Lesson could not be added", "error");
    }
  };

  const updateLesson = async (lesson: Lesson, patch: Partial<Lesson>) => {
    try {
      const updated = await academyAdminApi<Lesson>(`/lessons/${lesson.id}`, {
        method: "PUT",
        body: JSON.stringify(patch),
      });
      setLessonsByModule((current) => ({
        ...current,
        [lesson.moduleId]: (current[lesson.moduleId] || []).map((row) => row.id === updated.id ? updated : row),
      }));
    } catch (error) {
      flash(error instanceof Error ? error.message : "Lesson could not be saved", "error");
      throw error;
    }
  };

  const deleteLesson = async (lesson: Lesson) => {
    if (!window.confirm(`Delete lesson "${lesson.title}"?`)) return;
    try {
      await academyAdminApi(`/lessons/${lesson.id}`, { method: "DELETE" });
      setLessonsByModule((current) => ({
        ...current,
        [lesson.moduleId]: (current[lesson.moduleId] || []).filter((row) => row.id !== lesson.id),
      }));
      flash("Lesson deleted.");
    } catch (error) {
      flash(error instanceof Error ? error.message : "Lesson could not be deleted", "error");
    }
  };

  const filteredCourses = useMemo(() => {
    const term = search.trim().toLowerCase();
    return courses.filter((course) => {
      const matchesSearch = !term || [course.title, course.category, course.instructor].some((value) => String(value || "").toLowerCase().includes(term));
      const matchesStatus = statusFilter === "All" || course.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [courses, search, statusFilter]);

  const publishedCount = courses.filter((course) => course.status === "Published" || course.status === "Uploaded").length;
  const draftCount = courses.filter((course) => course.status === "Draft" || course.status === "Review").length;
  const customerAppCount = ecosystemApps.filter((app) => ["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing", "app-academy"].includes(app.id)).length;

  return (
    <div className="w-full max-w-[1500px] mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <section className="bg-[#0B1528] border border-slate-800 rounded-2xl p-6 text-white">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5">
          <div>
            <div className="text-cyan-400 text-[11px] font-bold uppercase tracking-wider">Platform administration</div>
            <h1 className="text-2xl font-extrabold mt-1">V79 Platform Admin</h1>
            <p className="text-sm text-slate-300 mt-2 max-w-2xl">
              Manage customer lifecycle, V79 applications, plans, Academy administration and audited platform controls from one place.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2 min-w-[330px]">
            <Metric label="Admin areas" value="6" />
            <Metric label="Customer apps" value={String(customerAppCount)} />
            <Metric label="Admin security" value="MFA" />
          </div>
        </div>
      </section>

      {message && (
        <div className={`rounded-xl border px-4 py-3 text-sm font-medium ${
          message.type === "success"
            ? "bg-emerald-50 border-emerald-200 text-emerald-800"
            : "bg-rose-50 border-rose-200 text-rose-800"
        }`}>
          {message.text}
        </div>
      )}

      <nav className="flex flex-wrap gap-2 border-b border-slate-200 pb-3" aria-label="Platform administration">
        <button onClick={() => { setSection("platform"); setPlatformView("overview"); }}
          className={`inline-flex items-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-semibold ${
            section === "platform" && platformView === "overview" ? "bg-slate-950 border-slate-950 text-white" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
          }`}>
          <Settings2 className="w-4 h-4" /> Overview
        </button>
        <button onClick={() => { setSection("platform"); setPlatformView("customers"); }}
          className={`inline-flex items-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-semibold ${
            section === "platform" && platformView === "customers" ? "bg-slate-950 border-slate-950 text-white" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
          }`}>
          <Users className="w-4 h-4" /> Customers
        </button>
        <button onClick={() => { setSection("platform"); setPlatformView("applications"); }}
          className={`inline-flex items-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-semibold ${
            section === "platform" && platformView === "applications" ? "bg-slate-950 border-slate-950 text-white" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
          }`}>
          <Layers3 className="w-4 h-4" /> Applications
        </button>
        <button onClick={() => { setSection("platform"); setPlatformView("plans"); }}
          className={`inline-flex items-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-semibold ${
            section === "platform" && platformView === "plans" ? "bg-slate-950 border-slate-950 text-white" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
          }`}>
          <CreditCard className="w-4 h-4" /> Plans & Entitlements
        </button>
        <button onClick={() => setSection("academy")}
          className={`inline-flex items-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-semibold ${
            section === "academy" ? "bg-slate-950 border-slate-950 text-white" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
          }`}>
          <GraduationCap className="w-4 h-4" /> Academy
        </button>
        <button onClick={() => { setSection("platform"); setPlatformView("audit"); }}
          className={`inline-flex items-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-semibold ${
            section === "platform" && platformView === "audit" ? "bg-slate-950 border-slate-950 text-white" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
          }`}>
          <ShieldCheck className="w-4 h-4" /> Audit & Security
        </button>
      </nav>

      {section === "platform" ? (
        <div className="space-y-4">
          {platformView === "overview" ? (
            <PlatformAdminOverview onOpen={(product) => {
              if (product === "academy") {
                setSection("academy");
                setAcademyView("courses");
              } else {
                setPlatformView("applications");
                setPlatformProductView(product);
              }
            }} />
          ) : platformView === "customers" ? (
            <PlatformCustomersAdmin />
          ) : platformView === "plans" ? (
            <PlatformPlansAdmin />
          ) : platformView === "audit" ? (
            <PlatformAuditAdmin />
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {[
                  ["pos", "POS"],
                  ["ffpro", "FFPRO"],
                  ["tiquet", "Tiquet"],
                  ["marketing", "Marketing"],
                ].map(([id, label]) => (
                  <button
                    key={id}
                    onClick={() => setPlatformProductView(id as PlatformProductView)}
                    className={`px-3 py-2 rounded-lg border text-xs font-semibold ${
                      platformProductView === id
                        ? "bg-slate-950 border-slate-950 text-white"
                        : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {label}
                  </button>
                ))}
                <button
                  onClick={() => { setSection("academy"); setAcademyView("courses"); }}
                  className="px-3 py-2 rounded-lg border border-slate-200 bg-white text-xs font-semibold text-slate-600 hover:bg-slate-50"
                >
                  Academy
                </button>
              </div>

              {platformProductView === "pos" ? (
                <POSPlatformAdmin />
              ) : platformProductView === "ffpro" ? (
                <FFPROPlatformAdmin />
              ) : platformProductView === "marketing" ? (
                <MarketingPlatformAdmin />
              ) : (
                <TiquetPlatformAdmin />
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {[
              ["courses", "Courses"],
              ["learners", "Learners"],
              ["publishing", "Publishing"],
              ["import", "Import"],
              ["junior", "Junior Academy"],
            ].map(([id, label]) => (
              <button
                key={id}
                onClick={() => setAcademyView(id as AcademyView)}
                className={`px-3 py-2 rounded-lg border text-xs font-semibold ${
                  academyView === id
                    ? "bg-slate-950 border-slate-950 text-white"
                    : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {academyView === "learners" ? (
            <AcademyLearners />
          ) : academyView === "publishing" ? (
            <AcademyPublishing courses={courses} onCoursesChanged={loadCourses} />
          ) : academyView === "import" ? (
            <AcademyImport onImported={loadCourses} />
          ) : academyView === "junior" ? (
            <AcademyJuniorAdmin courses={courses} />
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-[420px_minmax(0,1fr)] gap-5">
          <section className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
            <div className="p-4 border-b border-slate-200 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="font-bold text-slate-900">Course catalogue</h2>
                  <p className="text-xs text-slate-500 mt-0.5">{publishedCount} published · {draftCount} in progress</p>
                </div>
                <button onClick={startNewCourse} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-950 text-white text-xs font-semibold">
                  <Plus className="w-3.5 h-3.5" /> New course
                </button>
              </div>
              <div className="flex gap-2">
                <label className="relative flex-1">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                  <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search courses" className="admin-input pl-9" />
                </label>
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded-lg border border-slate-200 px-2 text-xs bg-white">
                  {["All", "Published", "Draft", "Review", "Imported", "Archived"].map((value) => <option key={value}>{value}</option>)}
                </select>
                <button onClick={() => void loadCourses()} className="p-2 border border-slate-200 rounded-lg text-slate-500 hover:bg-slate-50" title="Refresh">
                  <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
                </button>
              </div>
            </div>
            <div className="max-h-[720px] overflow-y-auto divide-y divide-slate-100">
              {filteredCourses.map((course) => (
                <button key={course.id} onClick={() => void selectCourse(course)} className={`w-full text-left p-4 hover:bg-slate-50 transition-colors ${selectedId === course.id ? "bg-cyan-50/70 border-l-2 border-cyan-500" : "border-l-2 border-transparent"}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-semibold text-sm text-slate-900 truncate">{course.title}</div>
                      <div className="text-[11px] text-slate-500 mt-1">{course.category || "General"} · {course.difficultyLevel || "Beginner"}</div>
                    </div>
                    <span className={`text-[9px] px-2 py-1 rounded-full border font-bold ${statusClass[course.status] || "bg-slate-100 border-slate-200 text-slate-600"}`}>{course.status}</span>
                  </div>
                  <div className="flex gap-4 mt-3 text-[10px] text-slate-400">
                    <span>{course.moduleCount || 0} modules</span>
                    <span>{course.lessonCount || 0} lessons</span>
                    <span>{course.pricingType === "free" ? "Free" : "Subscription"}</span>
                  </div>
                </button>
              ))}
              {!loading && filteredCourses.length === 0 && <div className="p-8 text-center text-sm text-slate-400">No courses match your filters.</div>}
            </div>
          </section>

          <section className="min-w-0 space-y-5">
            {!draft ? (
              <div className="bg-white border border-slate-200 rounded-2xl p-10 text-center">
                <BookOpen className="w-10 h-10 text-slate-300 mx-auto" />
                <h3 className="font-bold text-slate-800 mt-3">Select or create a course</h3>
                <p className="text-sm text-slate-500 mt-1">Course Builder administration now lives here in Hub Admin.</p>
              </div>
            ) : (
              <>
                <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 mb-5">
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">{selectedId ? "Edit course" : "Create course"}</div>
                      <h2 className="text-lg font-bold text-slate-900 mt-0.5">{draft.title || "Untitled course"}</h2>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {selectedId && <ActionButton onClick={duplicateCourse} icon={Copy} label="Duplicate" />}
                      {selectedId && draft.status !== "Archived" && <ActionButton onClick={archiveCourse} icon={Archive} label="Archive" />}
                      {selectedId && <ActionButton onClick={publishCourse} icon={Send} label="Publish" primary />}
                      <ActionButton onClick={saveCourse} icon={busy ? Loader2 : Save} label={busy ? "Saving..." : "Save"} primary disabled={busy} spin={busy} />
                      {selectedId && <ActionButton onClick={deleteCourse} icon={Trash2} label="Delete" danger />}
                      {!selectedId && <button onClick={() => setDraft(null)} className="p-2 rounded-lg border border-slate-200 text-slate-500"><X className="w-4 h-4" /></button>}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Field label="Course title"><input value={draft.title || ""} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className="admin-input" /></Field>
                    <Field label="Category"><input value={draft.category || ""} onChange={(e) => setDraft({ ...draft, category: e.target.value })} className="admin-input" /></Field>
                    <Field label="Difficulty">
                      <select value={draft.difficultyLevel || "Beginner"} onChange={(e) => setDraft({ ...draft, difficultyLevel: e.target.value })} className="admin-input">
                        {["Beginner", "Intermediate", "Advanced"].map((value) => <option key={value}>{value}</option>)}
                      </select>
                    </Field>
                    <Field label="Instructor"><input value={draft.instructor || ""} onChange={(e) => setDraft({ ...draft, instructor: e.target.value })} className="admin-input" /></Field>
                    <Field label="Version"><input value={draft.courseVersion || ""} onChange={(e) => setDraft({ ...draft, courseVersion: e.target.value })} className="admin-input" /></Field>
                    <Field label="Estimated duration"><input value={draft.estimatedDuration || ""} onChange={(e) => setDraft({ ...draft, estimatedDuration: e.target.value })} className="admin-input" /></Field>
                    <Field label="Access">
                      <select value={draft.pricingType || "free"} onChange={(e) => setDraft({ ...draft, pricingType: e.target.value as PricingType, price: e.target.value === "free" ? 0 : draft.price })} className="admin-input">
                        <option value="free">Free</option>
                        <option value="subscription">Subscription</option>
                        <option value="premium">Legacy premium</option>
                        <option value="free_trial">Legacy trial</option>
                      </select>
                    </Field>
                    <Field label="Price"><input type="number" min="0" step="0.01" disabled={draft.pricingType === "free"} value={draft.price || 0} onChange={(e) => setDraft({ ...draft, price: Number(e.target.value) })} className="admin-input disabled:bg-slate-100" /></Field>
                    <Field label="Short description" wide><textarea value={draft.shortDescription || ""} onChange={(e) => setDraft({ ...draft, shortDescription: e.target.value })} rows={2} className="admin-input" /></Field>
                    <Field label="Full description" wide><textarea value={draft.fullDescription || ""} onChange={(e) => setDraft({ ...draft, fullDescription: e.target.value })} rows={5} className="admin-input" /></Field>
                    <Field label="Learning objectives — one per line" wide><textarea value={(draft.learningObjectives || []).join("\n")} onChange={(e) => setDraft({ ...draft, learningObjectives: e.target.value.split("\n").map((v) => v.trim()).filter(Boolean) })} rows={4} className="admin-input" /></Field>
                    <Field label="Prerequisites — one per line" wide><textarea value={(draft.prerequisites || []).join("\n")} onChange={(e) => setDraft({ ...draft, prerequisites: e.target.value.split("\n").map((v) => v.trim()).filter(Boolean) })} rows={3} className="admin-input" /></Field>
                    <Field label="Thumbnail URL" wide><input value={draft.thumbnail || ""} onChange={(e) => setDraft({ ...draft, thumbnail: e.target.value })} className="admin-input" /></Field>
                  </div>
                </div>

                {selectedId && (
                  <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                    <div className="p-5 border-b border-slate-200 flex items-center justify-between">
                      <div>
                        <h3 className="font-bold text-slate-900">Modules & lessons</h3>
                        <p className="text-xs text-slate-500 mt-0.5">Build the course structure without leaving Hub.</p>
                      </div>
                      <button onClick={() => void addModule()} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 text-xs font-semibold hover:bg-slate-50">
                        <Plus className="w-3.5 h-3.5" /> Add module
                      </button>
                    </div>
                    <div className="divide-y divide-slate-100">
                      {modules.map((module) => (
                        <div key={module.id}>
                          <div className="p-4 flex items-center gap-3">
                            <button onClick={() => void toggleModule(module)} className="p-1 text-slate-500">
                              {expandedModules.has(module.id) ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                            </button>
                            <Layers3 className="w-4 h-4 text-cyan-600 shrink-0" />
                            <input defaultValue={module.title} onBlur={(e) => e.target.value !== module.title && void updateModule(module, { title: e.target.value })} className="flex-1 text-sm font-semibold bg-transparent border-0 outline-none focus:ring-0" />
                            <span className="text-[10px] text-slate-400">{(lessonsByModule[module.id] || []).length || "—"} lessons</span>
                            <button onClick={() => void addLesson(module)} className="p-1.5 text-slate-500 hover:text-cyan-700" title="Add lesson"><Plus className="w-4 h-4" /></button>
                            <button onClick={() => void deleteModule(module)} className="p-1.5 text-slate-400 hover:text-rose-600" title="Delete module"><Trash2 className="w-4 h-4" /></button>
                          </div>
                          {expandedModules.has(module.id) && (
                            <div className="bg-slate-50 border-t border-slate-100 px-4 py-3 space-y-3">
                              {(lessonsByModule[module.id] || []).map((lesson) => <LessonEditor key={lesson.id} lesson={lesson} onSave={updateLesson} onDelete={deleteLesson} />)}
                              {(lessonsByModule[module.id] || []).length === 0 && <div className="text-xs text-slate-400 px-8 py-4">No lessons in this module yet.</div>}
                            </div>
                          )}
                        </div>
                      ))}
                      {modules.length === 0 && <div className="p-8 text-center text-sm text-slate-400">No modules yet. Add the first module to start building the course.</div>}
                    </div>
                  </div>
                )}
              </>
            )}
          </section>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="bg-[#101D35] border border-slate-700/60 rounded-xl px-3 py-3 text-center"><div className="text-xl font-extrabold">{value}</div><div className="text-[9px] text-slate-400 mt-0.5">{label}</div></div>;
}

function Field({ label, children, wide = false }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return <label className={`space-y-1.5 ${wide ? "md:col-span-2" : ""}`}><span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</span>{children}</label>;
}

function ActionButton({ onClick, icon: Icon, label, primary, danger, disabled, spin }: { onClick: () => void | Promise<void>; icon: React.ComponentType<{ className?: string }>; label: string; primary?: boolean; danger?: boolean; disabled?: boolean; spin?: boolean }) {
  const style = danger ? "border-rose-200 text-rose-700 hover:bg-rose-50" : primary ? "bg-slate-950 border-slate-950 text-white hover:bg-slate-800" : "border-slate-200 text-slate-700 hover:bg-slate-50";
  return <button onClick={() => void onClick()} disabled={disabled} className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border text-xs font-semibold disabled:opacity-50 ${style}`}><Icon className={`w-3.5 h-3.5 ${spin ? "animate-spin" : ""}`} />{label}</button>;
}

function LessonEditor({ lesson, onSave, onDelete }: { lesson: Lesson; onSave: (lesson: Lesson, patch: Partial<Lesson>) => Promise<void>; onDelete: (lesson: Lesson) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(lesson);
  const [saving, setSaving] = useState(false);
  useEffect(() => setDraft(lesson), [lesson]);

  const save = async () => {
    setSaving(true);
    try {
      await onSave(lesson, draft);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="flex items-center gap-3 px-3 py-2.5">
        <button onClick={() => setOpen(!open)} className="p-1 text-slate-400">{open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}</button>
        <FileText className="w-4 h-4 text-indigo-500" />
        <div className="flex-1 min-w-0"><div className="text-xs font-semibold text-slate-800 truncate">{lesson.title}</div><div className="text-[10px] text-slate-400">{lesson.estimatedTime || "20 mins"}</div></div>
        <button onClick={() => void onDelete(lesson)} className="p-1.5 text-slate-400 hover:text-rose-600"><Trash2 className="w-3.5 h-3.5" /></button>
      </div>
      {open && (
        <div className="border-t border-slate-100 p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Lesson title"><input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className="admin-input" /></Field>
          <Field label="Estimated time"><input value={draft.estimatedTime || ""} onChange={(e) => setDraft({ ...draft, estimatedTime: e.target.value })} className="admin-input" /></Field>
          <Field label="Description" wide><textarea rows={2} value={draft.description || ""} onChange={(e) => setDraft({ ...draft, description: e.target.value })} className="admin-input" /></Field>
          <Field label="Lesson content" wide><textarea rows={8} value={draft.lessonContent || ""} onChange={(e) => setDraft({ ...draft, lessonContent: e.target.value })} className="admin-input font-mono text-[11px]" /></Field>
          <Field label="Video URL"><input value={draft.videoUrl || ""} onChange={(e) => setDraft({ ...draft, videoUrl: e.target.value })} className="admin-input" /></Field>
          <Field label="Audio URL"><input value={draft.audioUrl || ""} onChange={(e) => setDraft({ ...draft, audioUrl: e.target.value })} className="admin-input" /></Field>
          <Field label="Learning objectives — one per line" wide><textarea rows={3} value={(draft.learningObjectives || []).join("\n")} onChange={(e) => setDraft({ ...draft, learningObjectives: e.target.value.split("\n").map((value) => value.trim()).filter(Boolean) })} className="admin-input" /></Field>
          <Field label="Exercise prompt" wide><textarea rows={3} value={draft.exercisePrompt || ""} onChange={(e) => setDraft({ ...draft, exercisePrompt: e.target.value })} className="admin-input" /></Field>
          <div className="md:col-span-2">
            <QuizEditor lessonId={lesson.id} />
          </div>
          <div className="md:col-span-2 flex justify-end">
            <button onClick={() => void save()} disabled={saving} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-950 text-white text-xs font-semibold disabled:opacity-50">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} Save lesson
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


function QuizEditor({ lessonId }: { lessonId: string }) {
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    if (loaded) return;
    try {
      setQuiz(await academyAdminApi<Quiz | null>(`/lessons/${lessonId}/quiz`));
      setLoaded(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Quiz could not be loaded.");
    }
  };

  const toggle = async () => {
    if (!open) await load();
    setOpen(!open);
  };

  const ensureQuiz = () => {
    if (quiz) return quiz;
    const created: Quiz = {
      id: "",
      lessonId,
      title: "Lesson Assessment",
      passingScore: 80,
      questions: [],
    };
    setQuiz(created);
    return created;
  };

  const addQuestion = () => {
    const current = ensureQuiz();
    const next: QuizQuestion = {
      id: crypto.randomUUID(),
      questionText: "",
      questionType: "multiple_choice",
      options: ["Option A", "Option B"],
      correctAnswer: "Option A",
      explanation: "",
      orderNumber: current.questions.length + 1,
    };
    setQuiz({ ...current, questions: [...current.questions, next] });
  };

  const updateQuestion = (id: string, patch: Partial<QuizQuestion>) => {
    const current = ensureQuiz();
    setQuiz({
      ...current,
      questions: current.questions.map((question) => question.id === id ? { ...question, ...patch } : question),
    });
  };

  const removeQuestion = (id: string) => {
    const current = ensureQuiz();
    setQuiz({
      ...current,
      questions: current.questions
        .filter((question) => question.id !== id)
        .map((question, index) => ({ ...question, orderNumber: index + 1 })),
    });
  };

  const save = async () => {
    const current = ensureQuiz();
    setSaving(true);
    setError("");
    try {
      const saved = await academyAdminApi<Quiz>(`/lessons/${lessonId}/quiz`, {
        method: "POST",
        body: JSON.stringify({
          title: current.title,
          passingScore: Number(current.passingScore || 80),
          questions: current.questions,
        }),
      });
      setQuiz(saved);
      setLoaded(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Quiz could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button type="button" onClick={() => void toggle()} className="w-full px-3 py-2.5 flex items-center justify-between bg-slate-50 text-xs font-semibold text-slate-700">
        <span>Lesson quiz {quiz?.questions?.length ? `· ${quiz.questions.length} question(s)` : ""}</span>
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>
      {open && (
        <div className="p-3 space-y-3">
          {error && <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-2">{error}</div>}
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_140px] gap-2">
            <input value={quiz?.title || "Lesson Assessment"} onChange={(e) => setQuiz({ ...ensureQuiz(), title: e.target.value })} className="admin-input" placeholder="Quiz title" />
            <label className="flex items-center gap-2 text-xs text-slate-600">
              Pass %
              <input type="number" min="1" max="100" value={quiz?.passingScore || 80} onChange={(e) => setQuiz({ ...ensureQuiz(), passingScore: Number(e.target.value) })} className="admin-input w-20" />
            </label>
          </div>
          <div className="space-y-2">
            {(quiz?.questions || []).map((question) => (
              <div key={question.id} className="border border-slate-200 rounded-lg p-3 space-y-2">
                <div className="flex gap-2">
                  <input value={question.questionText} onChange={(e) => updateQuestion(question.id, { questionText: e.target.value })} className="admin-input flex-1" placeholder="Question" />
                  <select
                    value={question.questionType}
                    onChange={(e) => {
                      const type = e.target.value as QuizQuestion["questionType"];
                      updateQuestion(question.id, {
                        questionType: type,
                        options: type === "true_false" ? ["True", "False"] : question.options,
                        correctAnswer: type === "true_false" ? "True" : question.correctAnswer,
                      });
                    }}
                    className="admin-input w-40"
                  >
                    <option value="multiple_choice">Multiple choice</option>
                    <option value="true_false">True / false</option>
                  </select>
                  <button type="button" onClick={() => removeQuestion(question.id)} className="p-2 text-rose-600"><Trash2 className="w-4 h-4" /></button>
                </div>
                {question.questionType === "multiple_choice" ? (
                  <>
                    <textarea
                      rows={2}
                      value={question.options.join("\n")}
                      onChange={(e) => updateQuestion(question.id, { options: e.target.value.split("\n").map((v) => v.trim()).filter(Boolean) })}
                      className="admin-input"
                      placeholder="Options — one per line"
                    />
                    <input value={String(question.correctAnswer ?? "")} onChange={(e) => updateQuestion(question.id, { correctAnswer: e.target.value })} className="admin-input" placeholder="Correct answer — exact option text" />
                  </>
                ) : (
                  <select value={String(question.correctAnswer || "True")} onChange={(e) => updateQuestion(question.id, { correctAnswer: e.target.value })} className="admin-input">
                    <option value="True">True</option>
                    <option value="False">False</option>
                  </select>
                )}
                <textarea rows={2} value={question.explanation || ""} onChange={(e) => updateQuestion(question.id, { explanation: e.target.value })} className="admin-input" placeholder="Explanation shown after answering" />
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between">
            <button type="button" onClick={addQuestion} className="px-3 py-2 rounded-lg border border-slate-200 text-xs font-semibold inline-flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> Add question</button>
            <button type="button" disabled={saving} onClick={() => void save()} className="px-3 py-2 rounded-lg bg-indigo-600 text-white text-xs font-semibold disabled:opacity-50">
              {saving ? "Saving..." : "Save quiz"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="bg-[#101D35] border border-slate-700/60 rounded-xl px-3 py-3 text-center"><div className="text-xl font-extrabold">{value}</div><div className="text-[9px] text-slate-400 mt-0.5">{label}</div></div>;
}

function Tab({ active, onClick, icon: Icon, label }: { active: boolean; onClick: () => void; icon: React.ComponentType<{ className?: string }>; label: string }) {
  return <button onClick={onClick} className={`inline-flex items-center gap-2 px-4 py-3 text-xs font-semibold border-b-2 ${active ? "border-cyan-500 text-cyan-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}><Icon className="w-4 h-4" />{label}</button>;
}

function Field({ label, children, wide = false }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return <label className={`space-y-1.5 ${wide ? "md:col-span-2" : ""}`}><span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</span>{children}</label>;
}

function ActionButton({ onClick, icon: Icon, label, primary, danger, disabled, spin }: { onClick: () => void | Promise<void>; icon: React.ComponentType<{ className?: string }>; label: string; primary?: boolean; danger?: boolean; disabled?: boolean; spin?: boolean }) {
  const style = danger ? "border-rose-200 text-rose-700 hover:bg-rose-50" : primary ? "bg-slate-950 border-slate-950 text-white hover:bg-slate-800" : "border-slate-200 text-slate-700 hover:bg-slate-50";
  return <button onClick={() => void onClick()} disabled={disabled} className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border text-xs font-semibold disabled:opacity-50 ${style}`}><Icon className={`w-3.5 h-3.5 ${spin ? "animate-spin" : ""}`} />{label}</button>;
}

function LessonEditor({ lesson, onSave, onDelete }: { lesson: Lesson; onSave: (lesson: Lesson, patch: Partial<Lesson>) => Promise<void>; onDelete: (lesson: Lesson) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(lesson);
  const [saving, setSaving] = useState(false);
  useEffect(() => setDraft(lesson), [lesson]);

  const save = async () => {
    setSaving(true);
    try {
      await onSave(lesson, draft);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="flex items-center gap-3 px-3 py-2.5">
        <button onClick={() => setOpen(!open)} className="p-1 text-slate-400">{open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}</button>
        <FileText className="w-4 h-4 text-indigo-500" />
        <div className="flex-1 min-w-0"><div className="text-xs font-semibold text-slate-800 truncate">{lesson.title}</div><div className="text-[10px] text-slate-400">{lesson.estimatedTime || "20 mins"}</div></div>
        <button onClick={() => void onDelete(lesson)} className="p-1.5 text-slate-400 hover:text-rose-600"><Trash2 className="w-3.5 h-3.5" /></button>
      </div>
      {open && (
        <div className="border-t border-slate-100 p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Lesson title"><input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className="admin-input" /></Field>
          <Field label="Estimated time"><input value={draft.estimatedTime || ""} onChange={(e) => setDraft({ ...draft, estimatedTime: e.target.value })} className="admin-input" /></Field>
          <Field label="Description" wide><textarea rows={2} value={draft.description || ""} onChange={(e) => setDraft({ ...draft, description: e.target.value })} className="admin-input" /></Field>
          <Field label="Lesson content" wide><textarea rows={8} value={draft.lessonContent || ""} onChange={(e) => setDraft({ ...draft, lessonContent: e.target.value })} className="admin-input font-mono text-[11px]" /></Field>
          <Field label="Video URL"><input value={draft.videoUrl || ""} onChange={(e) => setDraft({ ...draft, videoUrl: e.target.value })} className="admin-input" /></Field>
          <Field label="Audio URL"><input value={draft.audioUrl || ""} onChange={(e) => setDraft({ ...draft, audioUrl: e.target.value })} className="admin-input" /></Field>
          <Field label="Learning objectives — one per line" wide><textarea rows={3} value={(draft.learningObjectives || []).join("\n")} onChange={(e) => setDraft({ ...draft, learningObjectives: e.target.value.split("\n").map((value) => value.trim()).filter(Boolean) })} className="admin-input" /></Field>
          <Field label="Exercise prompt" wide><textarea rows={3} value={draft.exercisePrompt || ""} onChange={(e) => setDraft({ ...draft, exercisePrompt: e.target.value })} className="admin-input" /></Field>
          <div className="md:col-span-2">
            <QuizEditor lessonId={lesson.id} />
          </div>
          <div className="md:col-span-2 flex justify-end">
            <button onClick={() => void save()} disabled={saving} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-950 text-white text-xs font-semibold disabled:opacity-50">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} Save lesson
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


function QuizEditor({ lessonId }: { lessonId: string }) {
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    if (loaded) return;
    try {
      setQuiz(await academyAdminApi<Quiz | null>(`/lessons/${lessonId}/quiz`));
      setLoaded(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Quiz could not be loaded.");
    }
  };

  const toggle = async () => {
    if (!open) await load();
    setOpen(!open);
  };

  const ensureQuiz = () => {
    if (quiz) return quiz;
    const created: Quiz = {
      id: "",
      lessonId,
      title: "Lesson Assessment",
      passingScore: 80,
      questions: [],
    };
    setQuiz(created);
    return created;
  };

  const addQuestion = () => {
    const current = ensureQuiz();
    const next: QuizQuestion = {
      id: crypto.randomUUID(),
      questionText: "",
      questionType: "multiple_choice",
      options: ["Option A", "Option B"],
      correctAnswer: "Option A",
      explanation: "",
      orderNumber: current.questions.length + 1,
    };
    setQuiz({ ...current, questions: [...current.questions, next] });
  };

  const updateQuestion = (id: string, patch: Partial<QuizQuestion>) => {
    const current = ensureQuiz();
    setQuiz({
      ...current,
      questions: current.questions.map((question) => question.id === id ? { ...question, ...patch } : question),
    });
  };

  const removeQuestion = (id: string) => {
    const current = ensureQuiz();
    setQuiz({
      ...current,
      questions: current.questions
        .filter((question) => question.id !== id)
        .map((question, index) => ({ ...question, orderNumber: index + 1 })),
    });
  };

  const save = async () => {
    const current = ensureQuiz();
    setSaving(true);
    setError("");
    try {
      const saved = await academyAdminApi<Quiz>(`/lessons/${lessonId}/quiz`, {
        method: "POST",
        body: JSON.stringify({
          title: current.title,
          passingScore: Number(current.passingScore || 80),
          questions: current.questions,
        }),
      });
      setQuiz(saved);
      setLoaded(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Quiz could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button type="button" onClick={() => void toggle()} className="w-full px-3 py-2.5 flex items-center justify-between bg-slate-50 text-xs font-semibold text-slate-700">
        <span>Lesson quiz {quiz?.questions?.length ? `· ${quiz.questions.length} question(s)` : ""}</span>
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>
      {open && (
        <div className="p-3 space-y-3">
          {error && <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-2">{error}</div>}
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_140px] gap-2">
            <input value={quiz?.title || "Lesson Assessment"} onChange={(e) => setQuiz({ ...ensureQuiz(), title: e.target.value })} className="admin-input" placeholder="Quiz title" />
            <label className="flex items-center gap-2 text-xs text-slate-600">
              Pass %
              <input type="number" min="1" max="100" value={quiz?.passingScore || 80} onChange={(e) => setQuiz({ ...ensureQuiz(), passingScore: Number(e.target.value) })} className="admin-input w-20" />
            </label>
          </div>
          <div className="space-y-2">
            {(quiz?.questions || []).map((question) => (
              <div key={question.id} className="border border-slate-200 rounded-lg p-3 space-y-2">
                <div className="flex gap-2">
                  <input value={question.questionText} onChange={(e) => updateQuestion(question.id, { questionText: e.target.value })} className="admin-input flex-1" placeholder="Question" />
                  <select
                    value={question.questionType}
                    onChange={(e) => {
                      const type = e.target.value as QuizQuestion["questionType"];
                      updateQuestion(question.id, {
                        questionType: type,
                        options: type === "true_false" ? ["True", "False"] : question.options,
                        correctAnswer: type === "true_false" ? "True" : question.correctAnswer,
                      });
                    }}
                    className="admin-input w-40"
                  >
                    <option value="multiple_choice">Multiple choice</option>
                    <option value="true_false">True / false</option>
                  </select>
                  <button type="button" onClick={() => removeQuestion(question.id)} className="p-2 text-rose-600"><Trash2 className="w-4 h-4" /></button>
                </div>
                {question.questionType === "multiple_choice" ? (
                  <>
                    <textarea
                      rows={2}
                      value={question.options.join("\n")}
                      onChange={(e) => updateQuestion(question.id, { options: e.target.value.split("\n").map((v) => v.trim()).filter(Boolean) })}
                      className="admin-input"
                      placeholder="Options — one per line"
                    />
                    <input value={String(question.correctAnswer ?? "")} onChange={(e) => updateQuestion(question.id, { correctAnswer: e.target.value })} className="admin-input" placeholder="Correct answer — exact option text" />
                  </>
                ) : (
                  <select value={String(question.correctAnswer || "True")} onChange={(e) => updateQuestion(question.id, { correctAnswer: e.target.value })} className="admin-input">
                    <option value="True">True</option>
                    <option value="False">False</option>
                  </select>
                )}
                <textarea rows={2} value={question.explanation || ""} onChange={(e) => updateQuestion(question.id, { explanation: e.target.value })} className="admin-input" placeholder="Explanation shown after answering" />
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between">
            <button type="button" onClick={addQuestion} className="px-3 py-2 rounded-lg border border-slate-200 text-xs font-semibold inline-flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> Add question</button>
            <button type="button" disabled={saving} onClick={() => void save()} className="px-3 py-2 rounded-lg bg-indigo-600 text-white text-xs font-semibold disabled:opacity-50">
              {saving ? "Saving..." : "Save quiz"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
