import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Wrench, ShieldAlert } from 'lucide-react';

export const CategoriesPage: React.FC = () => {
  const categoriesList = [
    {
      code: "ROADS",
      title: "Potholes and Damaged Roads",
      department: "Roads and Public Works",
      description: "Severe road surface defects, deep asphalt craters, structural cave-ins, and uneven surfaces that risk vehicular or two-wheeler safety.",
      defaultPriority: "P2 / P1 (if arterial road)",
      examples: ["Deep crater on highway junction", "Sunken manhole frame causing tire blowout", "Asphalt peeling on bus route"]
    },
    {
      code: "STREETLIGHTS",
      title: "Broken Streetlights & Electrical Poles",
      department: "Street Lighting & Electrical",
      description: "Non-functional streetlights, flickering sodium lamps, bent poles, sparking distribution junction boxes, and unlit pedestrian stretches.",
      defaultPriority: "P3 / P1 (if live wires exposed)",
      examples: ["Entire street dark for multiple consecutive nights", "Hanging high-voltage wire", "Damaged pole leaning over footpath"]
    },
    {
      code: "GARBAGE",
      title: "Garbage Accumulation & Illegal Dumping",
      department: "Sanitation & Solid Waste",
      description: "Overflowing community waste receptacles, uncollected domestic refuse, animal carcasses, and commercial debris dumped on public land.",
      defaultPriority: "P3",
      examples: ["Dumper bin overflowing across sidewalk", "Construction rubble dumped in vacant plot", "Rotting organic waste in market lane"]
    },
    {
      code: "DRAINAGE",
      title: "Drainage Blockages & Waterlogging",
      department: "Drainage & Flood Management",
      description: "Clogged stormwater drains, missing drain covers, reverse sewage flow, and monsoon street waterlogging that impedes transit.",
      defaultPriority: "P2 / P1 (if open manhole trap)",
      examples: ["Open drain without safety grate on school lane", "Water logging up to 1.5 feet after light rain", "Clogged sewer spewing onto road"]
    },
    {
      code: "WATER_SUPPLY",
      title: "Water Supply & Pipeline Leakage",
      department: "Water Supply & Distribution",
      description: "Burst municipal distribution pipelines, continuous potable water loss, low pressure supply disruptions, or contaminated tap water.",
      defaultPriority: "P2",
      examples: ["Water gushing out of cracked main line on avenue", "Severe water supply stoppage for 48 hours", "Muddy tap water supplied to block"]
    },
    {
      code: "FOOTPATHS",
      title: "Damaged Footpaths & Public Infrastructure",
      department: "Roads and Public Works",
      description: "Broken paver tiles, missing pedestrian kerbs, encroached walking paths, or broken guard rails causing pedestrian hazard.",
      defaultPriority: "P3 / P4",
      examples: ["Missing footpath slabs exposing 4-foot trench", "Broken pedestrian bridge railing", "Damaged curb ramps blocking wheelchairs"]
    },
    {
      code: "TREES_HAZARDS",
      title: "Fallen Trees & Public Hazards",
      department: "Parks & Urban Forestry",
      description: "Uprooted trees, large branches obstructing roads or electrical lines, and dead trees threatening public safety.",
      defaultPriority: "P1 (if blocking traffic) / P2",
      examples: ["Fallen banyan tree blocking both lanes", "Heavy branch cracked and hanging above power lines"]
    },
    {
      code: "SANITATION",
      title: "Public Sanitation Facilities",
      department: "Sanitation & Solid Waste",
      description: "Public toilets in unhygienic conditions, broken plumbing, lack of water supply in municipal restrooms, and open urination spots.",
      defaultPriority: "P3",
      examples: ["Public toilet locked or flooded", "Damaged septic tank in municipal market"]
    }
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 space-y-12">
      <div className="text-center max-w-2xl mx-auto space-y-3">
        <span className="text-xs font-bold uppercase tracking-wider text-brand-600">Municipal Service Directory</span>
        <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">Civic Issue Categories</h1>
        <p className="text-sm text-slate-600">
          Learn how each civic defect is categorized, which municipal department responds, and what priority SLA applies.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {categoriesList.map((item, idx) => (
          <div key={idx} className="bg-white p-7 rounded-3xl border border-slate-200 shadow-xs hover:border-brand-300 transition space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[11px] font-bold text-brand-600 uppercase tracking-wider">{item.department}</span>
                <h3 className="text-lg font-bold text-slate-900 mt-0.5">{item.title}</h3>
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-md bg-slate-100 text-slate-700">
                {item.defaultPriority}
              </span>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">{item.description}</p>

            <div className="pt-2 border-t border-slate-100">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1.5">Common Examples:</span>
              <ul className="space-y-1 text-xs text-slate-600">
                {item.examples.map((ex, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-brand-500"></span>
                    <span>{ex}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ))}
      </div>

      <div className="text-center pt-6">
        <Link
          to="/citizen/report"
          className="inline-flex items-center gap-2 px-6 py-3.5 bg-brand-600 hover:bg-brand-700 text-white rounded-xl font-semibold shadow-md transition"
        >
          <span>Report an Issue in One of These Categories</span>
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
};

