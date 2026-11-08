// flvertool: inspect a FLVER and re-save it with another header version (Nightreign 0x20021 -> Elden Ring 0x2001A).
//   flvertool info <file.flver>
//   flvertool convert <in.flver> <out.flver> [versionHex, default 2001A]
using System.Reflection;
using SoulsFormats;

// Walk up from the exe to the repo root (the folder holding tools/).
var root = new DirectoryInfo(AppContext.BaseDirectory);
while (root != null && !Directory.Exists(Path.Combine(root.FullName, "tools"))) root = root.Parent;
var smithbox = Path.Combine(root!.FullName, "tools", "Smithbox_2_2_6_2026_09_20_b");
AppDomain.CurrentDomain.AssemblyResolve += (_, e) =>
{
    var p = Path.Combine(smithbox, new AssemblyName(e.Name).Name + ".dll");
    return File.Exists(p) ? Assembly.LoadFrom(p) : null;
};
return Run(args);

static int Run(string[] args)
{
    if (args[0] == "oodle-debug")
    {
        var t = typeof(SFUtil).Assembly.GetType("SoulsFormats.Oodle");
        foreach (var f in t.GetFields(BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic))
            Console.WriteLine($"{f.Name} = {f.GetValue(null)}");
        foreach (var n in new[] { "CanUseOodle6", "CanUseOodle9" })
        {
            try { Console.WriteLine($"{n} -> {t.GetMethod(n, BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic).Invoke(null, null)}"); }
            catch (Exception e) { Console.WriteLine($"{n} threw {e.InnerException?.GetType().Name}: {e.InnerException?.Message}"); }
        }
        Console.WriteLine($"cwd {Environment.CurrentDirectory} base {AppContext.BaseDirectory}");
        return 0;
    }
    // regver <regulation.bin> [scanBlob]: print the regulation BND4 version; with scanBlob, try every 4-byte offset of a save blob.
    if (args[0] == "regver")
    {
        var data = File.ReadAllBytes(Path.GetFullPath(args[1]));
        Environment.CurrentDirectory = AppContext.BaseDirectory;
        int last = args.Length > 2 ? Math.Min(0x400, data.Length - 16) : 0;
        for (int off = 0; off <= last; off += 4)
        {
            try
            {
                var tmp = Path.GetTempFileName();
                File.WriteAllBytes(tmp, data.Skip(off).Take((data.Length - off) / 16 * 16).ToArray());
                var bnd = SFUtil.DecryptERRegulation(tmp);
                File.Delete(tmp);
                Console.WriteLine($"offset 0x{off:X}: version {bnd.Version} files {bnd.Files.Count}");
                return 0;
            }
            catch (Exception e) { if (last == 0) Console.WriteLine($"failed: {e.GetType().Name} {e.Message}"); }
        }
        Console.WriteLine("no regulation found");
        return 1;
    }
    // bxfextract <file.bhd> <file.bdt> <outDir> <nameRegex>: copy matching files out of a split archive (no full unpack).
    if (args[0] == "bxfextract")
    {
        args = args.Select((a, i) => i is 0 or 4 ? a : Path.GetFullPath(a)).ToArray();
        Environment.CurrentDirectory = AppContext.BaseDirectory;
        var bxf = BXF4.Read(args[1], args[2]);
        Directory.CreateDirectory(args[3]);
        foreach (var f in bxf.Files.Where(f => System.Text.RegularExpressions.Regex.IsMatch(f.Name, args[4])))
        {
            File.WriteAllBytes(Path.Combine(args[3], Path.GetFileName(f.Name.Replace('\\', '/'))), f.Bytes.ToArray());
            Console.WriteLine(f.Name);
        }
        return 0;
    }
    // gfxdump <file.gfx>: list the tags of a Scaleform GFX (SWF) file, descending into sprites.
    // taedump <file.tae> [animId...]: list animations (no ids) or each listed animation's events (type, times, params).
    if (args[0] == "taedump")
    {
        var tae = TAE.Read(Path.GetFullPath(args[1]));
        var want = args.Skip(2).Select(long.Parse).ToHashSet();
        Console.WriteLine($"TAE id {tae.ID} format {tae.Format} anims {tae.Animations.Count}");
        foreach (var a in tae.Animations.Where(a => want.Count == 0 || want.Contains(a.ID)))
        {
            var source = a.MiniHeader switch
            {
                TAE.Animation.AnimMiniHeader.Standard s => s.ImportsHKX ? $" clip from {s.ImportHKXSourceAnimID}" : "",
                TAE.Animation.AnimMiniHeader.ImportOtherAnim o => $" all from {o.ImportFromAnimID}",
                _ => "",
            };
            Console.WriteLine($"ANIM {a.ID} events {a.Events.Count} header {a.MiniHeader?.GetType().Name} file '{a.AnimFileName}'{source}");
            if (want.Count == 0) continue;
            foreach (var e in a.Events)
                Console.WriteLine($"  type {e.Type} {e.StartTime:0.###}-{e.EndTime:0.###} {Convert.ToHexString(e.GetParameterBytes(false))}");
        }
        return 0;
    }
    // taetsv <out.tsv> <tae dir>: every event of the TAEs in a folder as tab-separated group, anim, type, start, end, hex
    //   (group = number in the file name; for src/hero_report.py).
    if (args[0] == "taetsv")
    {
        var inv = System.Globalization.CultureInfo.InvariantCulture;
        using var w = new StreamWriter(args[1]);
        foreach (var f in Directory.GetFiles(args[2], "*.tae").Order())
        {
            var group = Path.GetFileNameWithoutExtension(f).TrimStart('a');
            foreach (var a in TAE.Read(Path.GetFullPath(f)).Animations)
            {
                w.WriteLine($"{group}\t{a.ID}\t-1\t0\t0\t");
                foreach (var e in a.Events)
                    w.WriteLine(string.Create(inv, $"{group}\t{a.ID}\t{e.Type}\t{e.StartTime}\t{e.EndTime}\t{Convert.ToHexString(e.GetParameterBytes(false))}"));
            }
        }
        return 0;
    }
    // portsfx <NR commoneffects.ffxbnd.dcx> <ER commoneffects.ffxbnd.dcx> <seed effect ids,> <out.txt> (from Merge's tool)
    //   Lists what the seeds need that Elden Ring lacks: the seeds, the effects those effects name (int32s in the FXR,
    //   recursively), and the textures and models their resource lists name. Lines: "effect <id>", "tex <name>", "model
    //   <name>". NR FXRs need src/port_fxr.py first, so this only lists; models are NR FLVERs ER can't draw as they are.
    if (args[0] == "portsfx")
    {
        args[1] = Path.GetFullPath(args[1]); args[2] = Path.GetFullPath(args[2]); args[4] = Path.GetFullPath(args[4]);
        Directory.SetCurrentDirectory(AppContext.BaseDirectory);
        var nr = BND4.Read(args[1]);
        var er = BND4.Read(args[2]);
        string Folder(BinderFile f) => Path.GetFileName(Path.GetDirectoryName(f.Name)!);
        string Stem(BinderFile f) => Path.GetFileNameWithoutExtension(f.Name).ToLowerInvariant();
        var nrFx = nr.Files.Where(f => Folder(f) == "effect").ToDictionary(Stem);
        var nrRes = nr.Files.Where(f => Folder(f) == "ResourceList").ToDictionary(Stem);
        var nrTex = nr.Files.Where(f => Folder(f) == "tex").ToDictionary(Stem);
        var nrModel = nr.Files.Where(f => Folder(f) == "model").ToDictionary(Stem);
        var erNames = er.Files.Select(f => Folder(f) + "/" + Stem(f)).ToHashSet();
        string FxName(long id) => $"f{id:D9}";
        bool Wanted(long id) => id >= 10000 && id < 1_000_000_000 && nrFx.ContainsKey(FxName(id)) && !erNames.Contains("effect/" + FxName(id));
        var seen = new HashSet<long>();
        var queue = new Queue<long>();
        foreach (var id in args[3].Split(',', StringSplitOptions.RemoveEmptyEntries).Select(long.Parse))
            if (Wanted(id) && seen.Add(id)) queue.Enqueue(id);
        var lines = new List<string>();
        var named = new HashSet<string>();
        while (queue.Count > 0)
        {
            var id = queue.Dequeue();
            lines.Add($"effect {id}");
            var bytes = nrFx[FxName(id)].Bytes.ToArray();
            for (int i = 0; i + 4 <= bytes.Length; i += 4)
            {
                long v = BitConverter.ToInt32(bytes, i);
                if (Wanted(v) && seen.Add(v)) queue.Enqueue(v);
            }
            if (!nrRes.TryGetValue(FxName(id), out var res)) continue;
            foreach (var r in System.Text.Encoding.ASCII.GetString(res.Bytes.ToArray()).Split('\n', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
            {
                var stem = Path.GetFileNameWithoutExtension(r).ToLowerInvariant();
                if (nrTex.ContainsKey(stem) && !erNames.Contains("tex/" + stem) && named.Add(stem)) lines.Add($"tex {stem}");
                else if (nrModel.ContainsKey(stem) && !erNames.Contains("model/" + stem) && named.Add(stem)) lines.Add($"model {stem}");
            }
        }
        File.WriteAllLines(args[4], lines);
        Console.WriteLine($"portsfx: {lines.Count} needed -> {args[4]}");
        return 0;
    }
    // adddummies <ER chrbnd> <NR chrbnd> <out chrbnd> (from Merge's tool): copies the dummy polys of NR's c0000.flver that
    //   ER's lacks (by reference id; ids ER already uses stay ER's), attached to the bones of the same names. NR effects
    //   spawn at these (e.g. Wylder's devices at 450-454); without them nothing shows.
    if (args[0] == "adddummies")
    {
        args[1] = Path.GetFullPath(args[1]); args[2] = Path.GetFullPath(args[2]); args[3] = Path.GetFullPath(args[3]);
        Directory.SetCurrentDirectory(AppContext.BaseDirectory);
        var er = BND4.Read(args[1]);
        var erFile = er.Files.Single(f => f.Name.EndsWith("c0000.flver", StringComparison.OrdinalIgnoreCase));
        var erFl = FLVER2.Read(erFile.Bytes);
        var nrFl = FLVER2.Read(BND4.Read(args[2]).Files.Single(f => f.Name.EndsWith("c0000.flver", StringComparison.OrdinalIgnoreCase)).Bytes);
        var have = erFl.Dummies.Select(d => d.ReferenceID).ToHashSet();
        short Bone(short nrIndex)  // the bone of the same name in ER's model; -2 when it has none
        {
            if (nrIndex < 0) return nrIndex;
            var name = nrFl.Nodes[nrIndex].Name;
            return (short)Math.Max(erFl.Nodes.FindIndex(n => n.Name == name), -2);
        }
        // A dummy's parent node may be named differently between the games (Japanese names): unmatched ones map to the
        // parent most of ER's own dummies use.
        var erParent = erFl.Dummies.GroupBy(d => d.ParentBoneIndex).MaxBy(g => g.Count())!.Key;
        short Parent(short nrIndex) { var b = Bone(nrIndex); return b == -2 ? erParent : b; }
        var added = new List<int>();
        foreach (var d in nrFl.Dummies.Where(d => !have.Contains(d.ReferenceID)))
        {
            if (Bone(d.AttachBoneIndex) == -2) { Console.WriteLine($"  skipped {d.ReferenceID}: no bone {nrFl.Nodes[d.AttachBoneIndex].Name}"); continue; }
            erFl.Dummies.Add(new FLVER.Dummy { Position = d.Position, Forward = d.Forward, Upward = d.Upward, ReferenceID = d.ReferenceID,
                ParentBoneIndex = Parent(d.ParentBoneIndex), AttachBoneIndex = Bone(d.AttachBoneIndex), FollowAttachBone = d.FollowAttachBone,
                UseUpwardVector = d.UseUpwardVector, Unk30 = d.Unk30, Unk34 = d.Unk34, Color = d.Color });
            have.Add(d.ReferenceID);
            added.Add(d.ReferenceID);
        }
        erFile.Bytes = erFl.Write();
        er.Write(args[3]);
        Console.WriteLine($"adddummies: {added.Count} added ({string.Join(" ", added)}) -> {args[3]}");
        return 0;
    }
    // taegraft <nr.tae> <er.tae> <out.tae> <animIds,> <spEffect map old=new,> <dropTypes,>
    //   Copy NR animation entries into an ER TAE. SpEffect events (type 67, first int = SpEffect id) are remapped by
    //   the map; ids mapped to 0 are dropped with their event. Events of dropTypes are removed. Existing ids refuse.
    if (args[0] == "taegraft")
    {
        var nr = TAE.Read(Path.GetFullPath(args[1]));
        var er = TAE.Read(Path.GetFullPath(args[2]));
        var ids = args[4].Split(',').Select(long.Parse).ToHashSet();
        var map = args[5].Split(',', StringSplitOptions.RemoveEmptyEntries).Select(s => s.Split('='))
            .ToDictionary(p => int.Parse(p[0]), p => int.Parse(p[1]));
        var drop = args[6].Split(',', StringSplitOptions.RemoveEmptyEntries).Select(int.Parse).ToHashSet();
        foreach (var a in nr.Animations.Where(a => ids.Contains(a.ID)))
        {
            if (er.Animations.Any(x => x.ID == a.ID)) throw new Exception($"ER already has anim {a.ID}");
            int dropped = 0, remapped = 0;
            foreach (var e in a.Events.ToList())
            {
                if (drop.Contains(e.Type)) { a.Events.Remove(e); dropped++; continue; }
                if (e.Type != 67) continue;
                var p = e.GetParameterBytes(false);
                int sp = BitConverter.ToInt32(p, 0);
                if (!map.TryGetValue(sp, out var to)) continue;
                if (to == 0) { a.Events.Remove(e); dropped++; continue; }
                BitConverter.GetBytes(to).CopyTo(p, 0);
                e.SetParameterBytes(false, p);
                remapped++;
            }
            er.Animations.Add(a);
            Console.WriteLine($"anim {a.ID}: {a.Events.Count} events, {remapped} SpEffects remapped, {dropped} dropped");
        }
        er.Animations.Sort((x, y) => x.ID.CompareTo(y.ID));
        er.Write(Path.GetFullPath(args[3]));
        return 0;
    }
    // taeaddevents <in.tae> <out.tae> <fromAnim> <toAnim> <spec,...>: copy events of one animation onto another.
    //   spec = type (all events of that type) or type:firstInt (e.g. 0:27 = JumpTable 27); `*` replaces all of
    //   toAnim's events with all of fromAnim's.
    if (args[0] == "taeaddevents")
    {
        var tae = TAE.Read(Path.GetFullPath(args[1]));
        var from = tae.Animations.SingleOrDefault(a => a.ID == long.Parse(args[3]));
        var to = tae.Animations.SingleOrDefault(a => a.ID == long.Parse(args[4]));
        if (from == null || to == null) { Console.WriteLine($"skip {args[3]} -> {args[4]} (not in this TAE)"); return 0; }
        bool all = args[5] == "*";
        float maxLen = args.Length > 6 ? float.Parse(args[6], System.Globalization.CultureInfo.InvariantCulture) : 0;  // only events this short
        if (all) to.Events.Clear();
        var specs = all ? new() : args[5].Split(',').Select(s => s.Split(':')).ToList();
        int n = 0;
        foreach (var e in from.Events.ToList())
        {
            var p = e.GetParameterBytes(false);
            if (!all && !specs.Any(s => int.Parse(s[0]) == e.Type && (s.Length == 1 || BitConverter.ToInt32(p, 0) == int.Parse(s[1]))))
                continue;
            if (maxLen > 0 && e.EndTime - e.StartTime > maxLen + 0.001f) continue;
            to.Events.Add(new TAE.Event(e.StartTime, e.EndTime, e.Type, e.Unk04, p, false));
            n++;
        }
        tae.Write(Path.GetFullPath(args[2]));
        Console.WriteLine($"anim {to.ID}: +{n} events from {from.ID}");
        return 0;
    }
    // taeclone <in.tae> <out.tae> <oldGroup> <newGroup> <spEffect map old=new,> <dropTypes,> [<keepIds,>]
    //   Copy a TAE as another animation group (TAE id 2000+group; imports from oldGroup point at newGroup).
    //   SpEffect events (type 66/67, first int) are remapped by the map, mapped-to-0 ones dropped. With keepIds only
    //   those animations stay (an override group should only time the clips it has).
    if (args[0] == "taeclone")
    {
        var tae = TAE.Read(Path.GetFullPath(args[1]));
        int oldG = int.Parse(args[3]), newG = int.Parse(args[4]);
        var map = args[5].Split(',', StringSplitOptions.RemoveEmptyEntries).Select(s => s.Split('='))
            .ToDictionary(p => int.Parse(p[0]), p => int.Parse(p[1]));
        var drop = args[6].Split(',', StringSplitOptions.RemoveEmptyEntries).Select(int.Parse).ToHashSet();
        tae.ID = 2000 + newG;
        if (args.Length > 7)
        {
            var keep = args[7].Split(',', StringSplitOptions.RemoveEmptyEntries).Select(long.Parse).ToHashSet();
            tae.Animations.RemoveAll(a => !keep.Contains(a.ID));
        }
        int dropped = 0, remapped = 0, imports = 0;
        foreach (var a in tae.Animations)
        {
            if (a.MiniHeader is TAE.Animation.AnimMiniHeader.ImportOtherAnim imp && imp.ImportFromAnimID / 1000000 == oldG)
            {
                imp.ImportFromAnimID = newG * 1000000 + imp.ImportFromAnimID % 1000000;
                imports++;
            }
            foreach (var e in a.Events.ToList())
            {
                if (drop.Contains(e.Type)) { a.Events.Remove(e); dropped++; continue; }
                if (e.Type != 66 && e.Type != 67) continue;
                var p = e.GetParameterBytes(false);
                if (!map.TryGetValue(BitConverter.ToInt32(p, 0), out var to)) continue;
                if (to == 0) { a.Events.Remove(e); dropped++; continue; }
                BitConverter.GetBytes(to).CopyTo(p, 0);
                e.SetParameterBytes(false, p);
                remapped++;
            }
        }
        tae.Write(Path.GetFullPath(args[2]));
        Console.WriteLine($"TAE {tae.ID}: {tae.Animations.Count} anims, {imports} imports moved, {remapped} SpEffects remapped, {dropped} events dropped");
        return 0;
    }
    // paramdump <file.param> <paramdef.xml> <out.xml> [ids,]: rows as <row id=".." field=".." /> (fields that differ
    //   from the paramdef default, like WitchyBND), for params WitchyBND can't read (e.g. Nightreign's Bullet).
    if (args[0] == "paramdump")
    {
        var param = PARAM.Read(Path.GetFullPath(args[1]));
        var def = PARAMDEF.XmlDeserialize(Path.GetFullPath(args[2]));
        if (!param.ApplyParamdefCarefully(def)) throw new Exception("paramdef does not match the param");
        var want = args.Length > 4 ? args[4].Split(',').Select(int.Parse).ToHashSet() : null;
        using var w = new StreamWriter(Path.GetFullPath(args[3]));
        w.WriteLine("<rows>");
        int n = 0;
        foreach (var row in param.Rows.Where(r => want == null || want.Contains(r.ID)))
        {
            var attrs = row.Cells.Where(c => !c.Def.InternalType.StartsWith("pad") && !Equals(c.Value, c.Def.Default)
                    && !(c.Value is byte[]))
                .Select(c => $"{c.Def.InternalName}=\"{System.Security.SecurityElement.Escape(Convert.ToString(c.Value, System.Globalization.CultureInfo.InvariantCulture))}\"");
            w.WriteLine($"<row id=\"{row.ID}\" {string.Join(" ", attrs)} />");
            n++;
        }
        w.WriteLine("</rows>");
        Console.WriteLine($"{n} rows");
        return 0;
    }
    // taesetsource <in.tae> <out.tae> <animIds,> <from> <to>: AttackBehavior (type 1) events' Source byte (offset 13).
    //   Nightreign's 3 = skill weapon / 4 = ultimate weapon don't exist in Elden Ring (0 default, 1 right, 2 left).
    if (args[0] == "taesetsource")
    {
        var tae = TAE.Read(Path.GetFullPath(args[1]));
        var ids = args[3].Split(',').Select(long.Parse).ToHashSet();
        byte from = byte.Parse(args[4]), to = byte.Parse(args[5]);
        int n = 0;
        foreach (var e in tae.Animations.Where(a => ids.Contains(a.ID)).SelectMany(a => a.Events).Where(e => e.Type == 1))
        {
            var p = e.GetParameterBytes(false);
            if (p.Length > 13 && p[13] == from) { p[13] = to; e.SetParameterBytes(false, p); n++; }
        }
        tae.Write(Path.GetFullPath(args[2]));
        Console.WriteLine($"{n} AttackBehavior events: source {from} -> {to}");
        return 0;
    }
    // taesetflag <in.tae> <out.tae> <animIds,> <from> <to>: ChrActionFlag (type 0) events' flag (first int).
    //   Nightreign's 146 "Ultimate IFrames" doesn't exist in Elden Ring, whose own clips use 94 "Perfect Invincibility".
    if (args[0] == "taesetflag")
    {
        var tae = TAE.Read(Path.GetFullPath(args[1]));
        var ids = args[3].Split(',').Select(long.Parse).ToHashSet();
        int from = int.Parse(args[4]), to = int.Parse(args[5]), n = 0;
        foreach (var e in tae.Animations.Where(a => ids.Contains(a.ID)).SelectMany(a => a.Events).Where(e => e.Type == 0))
        {
            var p = e.GetParameterBytes(false);
            if (BitConverter.ToInt32(p, 0) == from) { BitConverter.GetBytes(to).CopyTo(p, 0); e.SetParameterBytes(false, p); n++; }
        }
        tae.Write(Path.GetFullPath(args[2]));
        Console.WriteLine($"{n} ChrActionFlag events: {from} -> {to}");
        return 0;
    }
    // taetypes <file.tae>...: every event type used, with its parameter length(s) and count.
    // taesetbullet <in.tae> <out.tae> <animIds,> <fromSource> <toSource> <fromDummy> <toDummy> <judge map old=new,>: BulletBehavior
    //   (type 2) events: source byte 19; those on fromDummy move to toDummy; judges are remapped, unmapped ones removed. NR's
    //   ultimate fires from its hidden device weapon.
    if (args[0] == "taesetbullet")
    {
        var tae = TAE.Read(Path.GetFullPath(args[1]));
        var ids = args[3].Split(',').Select(long.Parse).ToHashSet();
        byte from = byte.Parse(args[4]), to = byte.Parse(args[5]);
        int fromDummy = int.Parse(args[6]), toDummy = int.Parse(args[7]), n = 0;
        var judges = args[8].Split(',').Select(s => s.Split('=')).ToDictionary(s => int.Parse(s[0]), s => int.Parse(s[1]));
        foreach (var a in tae.Animations.Where(a => ids.Contains(a.ID)))
            a.Events.RemoveAll(e => e.Type == 2 && !judges.ContainsKey(BitConverter.ToInt32(e.GetParameterBytes(false), 8)));
        foreach (var e in tae.Animations.Where(a => ids.Contains(a.ID)).SelectMany(a => a.Events).Where(e => e.Type == 2))
        {
            var p = e.GetParameterBytes(false);
            if (p.Length <= 19) continue;
            BitConverter.GetBytes(judges[BitConverter.ToInt32(p, 8)]).CopyTo(p, 8);
            p[19] = to;
            // Elden Ring's form, as a working Stake mod writes it (int 1 = -1, byte 18 = 0xFF); ER ignored 0 and 0.
            BitConverter.GetBytes(-1).CopyTo(p, 4);
            p[18] = 0xFF;
            if (BitConverter.ToInt32(p, 0) == fromDummy) BitConverter.GetBytes(toDummy).CopyTo(p, 0);
            e.SetParameterBytes(false, p);
            n++;
        }
        tae.Write(Path.GetFullPath(args[2]));
        Console.WriteLine($"{n} BulletBehavior events: source {from} -> {to}, dummy {fromDummy} -> {toDummy}");
        return 0;
    }
    if (args[0] == "taetypes")
    {
        var seen = new SortedDictionary<int, Dictionary<int, int>>();
        foreach (var path in args.Skip(1))
            foreach (var e in TAE.Read(Path.GetFullPath(path)).Animations.SelectMany(a => a.Events))
            {
                var lens = seen.TryGetValue(e.Type, out var d) ? d : seen[e.Type] = new();
                var n = e.GetParameterBytes(false).Length;
                lens[n] = lens.GetValueOrDefault(n) + 1;
            }
        foreach (var (t, lens) in seen)
            Console.WriteLine($"{t} " + string.Join(" ", lens.Select(kv => $"{kv.Key}b:{kv.Value}")));
        return 0;
    }
    if (args[0] == "gfxdump")
    {
        var b = File.ReadAllBytes(args[1]);
        int rectBits = b[8] >> 3, pos = 8 + (5 + rectBits * 4 + 7) / 8 + 4;
        Console.WriteLine($"{System.Text.Encoding.ASCII.GetString(b, 0, 3)} v{b[3]} len {BitConverter.ToUInt32(b, 4)} (file {b.Length}) frames {BitConverter.ToUInt16(b, pos - 2)}");
        Gfx.Dump(b, pos, b.Length, "");
        return 0;
    }
    // gfxaddframe <in.gfx> <out.gfx> <spriteId> <templateImage> <newImage>...: for each new image, add an external image
    // (copy of the template's tag, new character id and name) and append a frame to the sprite that shows it, made like
    // the sprite's last frame. Class portraits: sprite 93 in 04_200_chrmake_basechrselect.gfx, frame = imageId - 1.
    if (args[0] == "gfxaddframe")
    {
        var b = File.ReadAllBytes(args[1]).ToList();
        int spriteId = int.Parse(args[3]);
        foreach (var name in args.Skip(5))
            Gfx.AddFrame(b, spriteId, args[4], name);
        var arr = b.ToArray();
        BitConverter.GetBytes(arr.Length).CopyTo(arr, 4);
        File.WriteAllBytes(args[2], arr);
        return 0;
    }
    // fxrcheck [-xml outDir] <file.fxr>...: FXR3 version enum, header bytes, and whether SoulsFormats reads and
    // round-trips each file. Nightreign files (byte 4 = 1, SoulsFormats asserts 0) are read with that byte zeroed.
    if (args[0] == "fxrcheck")
    {
        var vt = typeof(SFUtil).Assembly.GetType("SoulsFormats.FXR3+FXRVersion");
        if (vt != null) Console.WriteLine("FXRVersion: " + string.Join(", ", Enum.GetValues(vt).Cast<object>().Select(v => $"{v}={Convert.ToInt32(v)}")));
        string xmlDir = args[1] == "-xml" ? args[2] : null;
        foreach (var f in args.Skip(xmlDir == null ? 1 : 3))
        {
            var b = File.ReadAllBytes(f);
            byte b4 = b[4];
            b[4] = 0;
            try
            {
                var fxr = FXR3.Read(b);
                var w = fxr.Write();
                int diff = Enumerable.Range(0, Math.Min(b.Length, w.Length)).Count(i => b[i] != w[i]);
                Console.WriteLine($"{Path.GetFileName(f)}: byte4 {b4:X2} ver {fxr.Version} len {b.Length} -> {w.Length} diffbytes {diff}");
                if (xmlDir != null)
                {
                    Directory.CreateDirectory(xmlDir);
                    using var fs = File.Create(Path.Combine(xmlDir, Path.GetFileName(f) + $".b{b4}.xml"));
                    new System.Xml.Serialization.XmlSerializer(typeof(FXR3)).Serialize(fs, fxr);
                }
            }
            catch (Exception e) { Console.WriteLine($"{Path.GetFileName(f)}: byte4 {b4:X2} read failed: {e.GetType().Name}: {e.Message}"); }
        }
        return 0;
    }
    // fxrfromxml <in.xml> <out.fxr>...: write FXR3 XML (fxrcheck -xml, edited by port_fxr.py) back as Elden Ring FXR.
    if (args[0] == "fxrfromxml")
    {
        for (int i = 1; i + 1 < args.Length; i += 2)
        {
            using var fs = File.OpenRead(args[i]);
            var fxr = (FXR3)new System.Xml.Serialization.XmlSerializer(typeof(FXR3)).Deserialize(fs);
            File.WriteAllBytes(args[i + 1], fxr.Write());
        }
        return 0;
    }
    // memscan <pid> <hex> [dumpBytes]: find a byte pattern in a running process's readable memory (which param copy the game uses).
    if (args[0] == "memscan")
    {
        var pat = Convert.FromHexString(args[2].Replace(" ", ""));
        int dump = args.Length > 3 ? int.Parse(args[3]) : 64;
        var h = Native.OpenProcess(0x0410, false, int.Parse(args[1]));
        if (h == 0) { Console.WriteLine("OpenProcess failed"); return 1; }
        long addr = 0, hits = 0, regions = 0, failed = 0, total = 0;
        while (Native.VirtualQueryEx(h, addr, out var mbi, System.Runtime.InteropServices.Marshal.SizeOf<Native.MBI>()) != 0)
        {
            bool readable = mbi.State == 0x1000 && (mbi.Protect & 0x66) != 0 && (mbi.Protect & 0x100) == 0;
            if (readable) regions++;
            // Read in 64 MB chunks that overlap by a little, so a hit on a chunk border is still found.
            const long chunk = 64L << 20;
            for (long start = 0; readable && start < mbi.RegionSize; start += chunk)
            {
                var buf = new byte[Math.Min(chunk + 4096, mbi.RegionSize - start)];
                bool ok = Native.ReadProcessMemory(h, mbi.BaseAddress + start, buf, buf.Length, out var read);
                if (!ok) { failed++; continue; }
                total += Math.Min(read, chunk);
                for (int i = buf.AsSpan(0, (int)read).IndexOf(pat); i >= 0 && i < chunk && hits < 50;)
                {
                    hits++;
                    Console.WriteLine($"0x{mbi.BaseAddress + start + i:X}: {Convert.ToHexString(buf, i, Math.Min(dump, (int)read - i))}");
                    int next = buf.AsSpan(i + 1, (int)read - i - 1).IndexOf(pat);
                    i = next < 0 ? -1 : i + 1 + next;
                }
            }
            addr = mbi.BaseAddress + mbi.RegionSize;
        }
        Console.WriteLine($"{hits} hits in {regions} regions, {total >> 20} MB read, {failed} failed (last error {System.Runtime.InteropServices.Marshal.GetLastWin32Error()}, stopped at 0x{addr:X})");
        return 0;
    }
    if (args.Length < 2) { Console.Error.WriteLine("usage: info <flver> | convert <in> <out> [verHex]"); return 1; }
    // regpack <orig regulation.bin> <out> <files...> / bndpack <orig.dcx> <out> <files...>:
    // replace files (matched by file name) inside the original archive, keeping its order, ids and compression.
    if (args[0] == "regpack" || args[0] == "bndpack")
    {
        // SoulsFormats looks for oo2core_*.dll in the current directory: resolve paths, then run from the exe folder.
        args = args.Select((a, i) => i == 0 ? a : Path.GetFullPath(a)).ToArray();
        Environment.CurrentDirectory = AppContext.BaseDirectory;
        var reg = args[0] == "regpack";
        var bnd = reg ? SFUtil.DecryptERRegulation(args[1]) : BND4.Read(args[1]);
        foreach (var path in args.Skip(3))
        {
            var name = Path.GetFileName(path);
            var file = bnd.Files.Single(f => Path.GetFileName(f.Name.Replace('\\', '/')).Equals(name, StringComparison.OrdinalIgnoreCase));
            file.Bytes = File.ReadAllBytes(path);
            Console.WriteLine($"replaced {file.Name}");
        }
        if (reg) SFUtil.EncryptERRegulation(args[2], bnd); else bnd.Write(args[2]);
        return 0;
    }
    var flver = FLVER2.Read(args[1]);
    if (args[0] == "info")
    {
        var h = flver.Header;
        Console.WriteLine($"version 0x{h.Version:X} bones {flver.Nodes.Count} meshes {flver.Meshes.Count} materials {flver.Materials.Count} gxlists {flver.GXLists.Count} bufferLayouts {flver.BufferLayouts.Count}");
        Console.WriteLine($"bbox {h.BoundingBoxMin} .. {h.BoundingBoxMax}");
        foreach (var m in flver.Materials)
        {
            Console.WriteLine($"MAT {m.Name} | {m.MTD}");
            foreach (var t in m.Textures)
                Console.WriteLine("   " + string.Join(" ", t.GetType().GetProperties().Select(p => $"{p.Name}={p.GetValue(t)}")));
        }
        foreach (var mesh in flver.Meshes)
            Console.WriteLine($"MESH mat {mesh.MaterialIndex} verts {mesh.Vertices.Count} bufs {mesh.VertexBuffers.Count} layout {string.Join(",", mesh.VertexBuffers.Select(b => b.LayoutIndex))} facesets {mesh.FaceSets.Count} boxes {(mesh.BoundingBox == null ? "none" : "yes")}");
        foreach (var bl in flver.BufferLayouts)
            Console.WriteLine("LAYOUT " + string.Join(" ", bl.Select(m => $"{m.Semantic}{m.Index}:{m.Type}")));
        if (args.Length > 2 && args[2] == "bones")
            Console.WriteLine("BONES " + string.Join(" ", flver.Nodes.Take(12).Select(n => n.Name)));
        return 0;
    }
    if (args[0] == "detail")
    {
        Console.WriteLine("HEADER " + string.Join(" ", flver.Header.GetType().GetFields().Select(f => $"{f.Name}={Fmt(f.GetValue(flver.Header))}"))
            + " " + string.Join(" ", flver.Header.GetType().GetProperties().Select(p => $"{p.Name}={Fmt(p.GetValue(flver.Header))}")));
        var n0 = flver.Nodes[0];
        Console.WriteLine("NODE0 " + string.Join(" ", n0.GetType().GetProperties().Select(p => $"{p.Name}={Fmt(p.GetValue(n0))}")));
        Console.WriteLine("UNK06 " + string.Join(" | ", flver.Meshes.Select(m => string.Join(",", m.FaceSets.Select(f => f.Unk06)))));
        var fs0 = flver.Meshes[0].FaceSets[0];
        Console.WriteLine("FACESET0 " + string.Join(" ", fs0.GetType().GetProperties().Where(p => p.Name != "Indices").Select(p => $"{p.Name}={Fmt(p.GetValue(fs0))}")));
        for (int g = 0; g < flver.GXLists.Count; g++)
            Console.WriteLine($"GXLIST {g}: " + string.Join(" ", flver.GXLists[g].Select(i => $"{i.ID}/{i.Unk04}/{i.Data.Length}")));
        foreach (var m in flver.Materials) Console.WriteLine($"MAT {m.Name} gx {m.GXIndex} idx {m.Index}");
        for (int i = 0; i < flver.Meshes.Count; i++)
        {
            var mesh = flver.Meshes[i];
            Console.WriteLine($"MESH {i} node {mesh.NodeIndex} boneIdx {mesh.BoneIndices.Count} dynamic {mesh.Dynamic} facesets " +
                string.Join(",", mesh.FaceSets.Select(f => $"{f.Flags}:{f.Indices.Count}:{(f.CullBackfaces ? "cull" : "nocull")}:{f.TriangleStrip}")));
            var v = mesh.Vertices[0];
            Console.WriteLine("   v0 " + string.Join(" ", v.GetType().GetFields().Select(f => $"{f.Name}={Fmt(f.GetValue(v))}")));
        }
        return 0;
    }
    if (args[0] == "convert")
    {
        ToEldenRing(flver);
        flver.Header.Version = args.Length > 3 ? Convert.ToInt32(args[3], 16) : 0x2001A;
        flver.Write(args[2]);
        var back = FLVER2.Read(args[2]);
        Console.WriteLine($"wrote {args[2]} version 0x{back.Header.Version:X} meshes {back.Meshes.Count} layouts {back.BufferLayouts.Count}");
        return 0;
    }
    if (args[0] == "stub")
    {
        // Invisible placeholder: keep the skeleton and one mesh holding a single zero-area triangle.
        var mesh = flver.Meshes[0];
        // Three distinct vertex objects: SoulsFormats keeps per-vertex write queues, so one shared object breaks Write.
        mesh.Vertices = mesh.Vertices.Take(3).ToList();
        foreach (var v in mesh.Vertices) v.Position = System.Numerics.Vector3.Zero;
        foreach (var fs in mesh.FaceSets) fs.Indices = new List<int> { 0, 1, 2 };
        flver.Meshes = new List<FLVER2.Mesh> { mesh };
        flver.Materials = new List<FLVER2.Material> { flver.Materials[mesh.MaterialIndex] };
        mesh.MaterialIndex = 0;
        flver.Write(args[2]);
        Console.WriteLine($"wrote stub {args[2]} nodes {FLVER2.Read(args[2]).Nodes.Count}");
        return 0;
    }
    Console.Error.WriteLine("unknown command");
    return 1;
}

// Rebuild Nightreign's split vertex streams into the interleaved layouts Elden Ring's own parts use,
// and add the MotionBlur face sets ER meshes carry (copies of the LOD sets, as some vanilla ER meshes have).
static void ToEldenRing(FLVER2 flver)
{
    FLVER.LayoutMember M(FLVER.LayoutType t, FLVER.LayoutSemantic s, int i = 0) => new FLVER.LayoutMember(t, s, i, 0);
    var F3 = FLVER.LayoutType.Float3; var B4 = FLVER.LayoutType.UByte4; var B4N = FLVER.LayoutType.UByte4Norm; var S4 = FLVER.LayoutType.Short4;
    var P = FLVER.LayoutSemantic.Position; var N = FLVER.LayoutSemantic.Normal; var T = FLVER.LayoutSemantic.Tangent;
    var BT = FLVER.LayoutSemantic.Bitangent; var BI = FLVER.LayoutSemantic.BoneIndices; var BW = FLVER.LayoutSemantic.BoneWeights;
    var VC = FLVER.LayoutSemantic.VertexColor; var UV = FLVER.LayoutSemantic.UV;

    var regular = new[] { M(F3, P), M(B4, N), M(B4, T), M(B4, BI), M(B4N, BW), M(B4N, VC, 1), M(S4, UV) };
    var weapon = new[] { M(F3, P), M(B4, N), M(B4, T), M(B4N, VC, 1), M(S4, UV) };
    var clothA = new[] { M(F3, P), M(B4, N), M(B4, T) };
    var clothB = new[] { M(B4, BT), M(B4, BI), M(B4N, BW), M(B4N, VC, 1), M(S4, UV) };
    var clothC = new[] { M(F3, P, 1), M(B4, N, 1), M(B4, T, 1) };

    var oldLayouts = flver.BufferLayouts;
    var layouts = new List<FLVER2.BufferLayout>();
    int LayoutIndex(IEnumerable<FLVER.LayoutMember> members)
    {
        var key = string.Join(" ", members.Select(m => $"{m.Semantic}{m.Index}:{m.Type}"));
        int i = layouts.FindIndex(l => string.Join(" ", l.Select(m => $"{m.Semantic}{m.Index}:{m.Type}")) == key);
        if (i >= 0) return i;
        var bl = new FLVER2.BufferLayout();
        bl.AddRange(members.Select(m => M(m.Type, m.Semantic, m.Index)));
        layouts.Add(bl);
        return layouts.Count - 1;
    }

    var red = new FLVER.VertexColor(1f, 1f, 0f, 0f); // (A, R, G, B): ER parts use R=1 G=0 B=0 A=1
    foreach (var mesh in flver.Meshes)
    {
        var members = mesh.VertexBuffers.SelectMany(b => oldLayouts[b.LayoutIndex]).ToList();
        bool cloth = members.Any(m => m.Semantic == P && m.Index == 1);
        bool hasColor = members.Any(m => m.Semantic == VC);
        int uvCount = members.Count(m => m.Semantic == UV);
        int maxBone = mesh.Vertices.Max(v => Math.Max(Math.Max(v.BoneIndices[0], v.BoneIndices[1]), Math.Max(v.BoneIndices[2], v.BoneIndices[3])));
        if (maxBone > 255) throw new Exception($"bone index {maxBone} does not fit UByte4");

        List<int> newBuffers;
        if (cloth)
            newBuffers = new() { LayoutIndex(clothA), LayoutIndex(clothB), LayoutIndex(clothC) };
        else if (hasColor || uvCount > 1)
            newBuffers = new() { LayoutIndex(members) }; // special shaders (fur): keep NR's semantics, one interleaved stream
        else if (mesh.Dynamic == 0)
            newBuffers = new() { LayoutIndex(weapon) };
        else
            newBuffers = new() { LayoutIndex(regular) };

        foreach (var v in mesh.Vertices)
        {
            if (!hasColor) v.Colors = new List<FLVER.VertexColor> { red };
            if (cloth)
            {
                while (v.Tangents.Count < 2) v.Tangents.Add(v.Tangents[0]);
                v.Bitangent = new System.Numerics.Vector4(-1, -1, -1, -1);
            }
        }
        mesh.VertexBuffers = newBuffers.Select(i => new FLVER2.VertexBuffer(i)).ToList();

        // ER face sets carry Unk06 = 1 on static meshes and, on skinned ones, what matches the number of distinct bones used.
        short boneCount = mesh.Dynamic == 0 ? (short)1 : (short)mesh.Vertices
            .SelectMany(v => Enumerable.Range(0, 4).Where(k => v.BoneWeights[k] > 0).Select(k => v.BoneIndices[k])).Distinct().Count();
        foreach (var f in mesh.FaceSets) f.Unk06 = boneCount;
        var lods = mesh.FaceSets.Where(f => (f.Flags & FLVER2.FaceSet.FSFlags.MotionBlur) == 0).ToList();
        if (lods.Count == mesh.FaceSets.Count)
            foreach (var f in lods)
                mesh.FaceSets.Add(new FLVER2.FaceSet(f.Flags | FLVER2.FaceSet.FSFlags.MotionBlur, f.TriangleStrip, f.CullBackfaces, f.Unk06, new List<int>(f.Indices)));
    }
    flver.BufferLayouts = layouts;

    // Header values and material paths as in ER's own parts (NR writes Unk68=0, Unk74=16 and bare matxml names).
    flver.Header.Unk68 = 4;
    flver.Header.Unk74 = 0;
    foreach (var m in flver.Materials)
        if (!m.MTD.Contains('\\')) m.MTD = @"N:\GR\data\Material\mtd\Parts\matxml\" + m.MTD;
}

static string Fmt(object o) => o is System.Collections.IEnumerable e && o is not string
    ? "[" + string.Join(";", e.Cast<object>()) + "]" : o?.ToString();

static class Gfx
{
    public static IEnumerable<(int Code, int Start, int Body, int Len)> Tags(byte[] b, int pos, int end)
    {
        while (pos + 2 <= end)
        {
            int head = BitConverter.ToUInt16(b, pos), code = head >> 6, len = head & 0x3F, body = pos + 2;
            if (len == 0x3F) { len = BitConverter.ToInt32(b, body); body += 4; }
            yield return (code, pos, body, len);
            if (code == 0) yield break;
            pos = body + len;
        }
    }

    public static void Dump(byte[] b, int pos, int end, string indent)
    {
        int frame = 0;
        foreach (var t in Tags(b, pos, end))
        {
            string info = t.Code switch
            {
                1 => $"ShowFrame #{frame++}",
                39 => $"DefineSprite id {BitConverter.ToUInt16(b, t.Body)} frames {BitConverter.ToUInt16(b, t.Body + 2)}",
                43 => "FrameLabel " + CStr(b, t.Body),
                26 or 70 => $"PlaceObject{(t.Code == 26 ? 2 : 3)} flags 0x{b[t.Body]:X2} {Convert.ToHexString(b, t.Body, Math.Min(t.Len, 16))}",
                28 => $"RemoveObject2 depth {BitConverter.ToUInt16(b, t.Body)}",
                1009 => $"DefineExternalImage2 {Convert.ToHexString(b, t.Body, Math.Min(t.Len, 12))} '{Names(b, t.Body, t.Len)}'",
                _ => $"len {t.Len} {Convert.ToHexString(b, t.Body, Math.Min(t.Len, 12))}",
            };
            Console.WriteLine($"{indent}@{t.Start:X} tag {t.Code} {info}");
            if (t.Code == 39) Dump(b, t.Body + 4, t.Body + t.Len, indent + "  ");
        }
    }

    static int Start(byte[] b) => 8 + (5 + (b[8] >> 3) * 4 + 7) / 8 + 4;

    static byte[] Tag(int code, byte[] body)
    {
        var head = new List<byte>(BitConverter.GetBytes((ushort)(code << 6 | 0x3F)));
        head.AddRange(BitConverter.GetBytes(body.Length));
        head.AddRange(body);
        return head.ToArray();
    }

    public static void AddFrame(List<byte> list, int spriteId, string template, string name)
    {
        var b = list.ToArray();
        var top = Tags(b, Start(b), b.Length).ToList();
        // Template image tag: u32 id, u16 format, u16 width, u16 height, then u8-length export name and file name.
        var img = top.First(t => t.Code == 1009 && Names(b, t.Body, t.Len).Contains("|" + template + "|"));
        int newId = top.Where(t => t.Code is 2 or 22 or 32 or 83 or 39 or 37 or 1009 or 46 or 84 or 10 or 48 or 75 or 11 or 33)
                       .Max(t => BitConverter.ToUInt16(b, t.Body)) + 1;
        var body = new List<byte>(BitConverter.GetBytes(newId));
        body.AddRange(b.Skip(img.Body + 4).Take(6));
        int at = img.Body + 10 + 1 + b[img.Body + 10];               // after the export name
        int tail = img.Body + img.Len - (at + 1 + b[at]);           // bytes after the file name
        foreach (var s in new[] { name, name + ".tga" }) { body.Add((byte)s.Length); body.AddRange(System.Text.Encoding.ASCII.GetBytes(s)); }
        body.AddRange(b.Skip(img.Body + img.Len - tail).Take(tail));
        var imgTag = Tag(1009, body.ToArray());

        // Sprite: replay its last frame's tags (RemoveObject2 + PlaceObject3) with the new id, then ShowFrame.
        var spr = top.First(t => t.Code == 39 && BitConverter.ToUInt16(b, t.Body) == spriteId);
        var inner = Tags(b, spr.Body + 4, spr.Body + spr.Len).ToList();
        int lastShow = inner.FindLastIndex(t => t.Code == 1), prevShow = inner.FindLastIndex(lastShow - 1, t => t.Code == 1);
        var frame = new List<byte>();
        foreach (var t in inner.Skip(prevShow + 1).Take(lastShow - prevShow))
        {
            var bytes = b.Skip(t.Start).Take(t.Body + t.Len - t.Start).ToArray();
            if (t.Code == 70) BitConverter.GetBytes((ushort)newId).CopyTo(bytes, t.Body - t.Start + 4); // flags, flags2, depth, id
            if (t.Code == 26) BitConverter.GetBytes((ushort)newId).CopyTo(bytes, t.Body - t.Start + 3);
            frame.AddRange(bytes);
        }
        var end = inner.Last(); // End tag
        var sprBody = b.Skip(spr.Body).Take(end.Start - spr.Body).Concat(frame).Concat(b.Skip(end.Start).Take(2)).ToArray();
        BitConverter.GetBytes((ushort)(BitConverter.ToUInt16(b, spr.Body + 2) + 1)).CopyTo(sprBody, 2);
        var sprTag = Tag(39, sprBody);

        // Rebuild: image tag goes right after the template's, sprite tag replaces the old one (sprite comes later).
        var outList = new List<byte>();
        outList.AddRange(b.Take(img.Body + img.Len));
        outList.AddRange(imgTag);
        outList.AddRange(b.Skip(img.Body + img.Len).Take(spr.Start - (img.Body + img.Len)));
        outList.AddRange(sprTag);
        outList.AddRange(b.Skip(spr.Body + spr.Len));
        list.Clear();
        list.AddRange(outList);
        Console.WriteLine($"{name}: image id {newId}, sprite {spriteId} now {BitConverter.ToUInt16(sprBody, 2)} frames");
    }

    static string CStr(byte[] b, int at) { int e = Array.IndexOf(b, (byte)0, at); return System.Text.Encoding.ASCII.GetString(b, at, e - at); }
    static string Names(byte[] b, int at, int len) =>
        System.Text.RegularExpressions.Regex.Replace(System.Text.Encoding.ASCII.GetString(b, at, len), @"[^\x20-\x7E]+", "|");
}

static class Native
{
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    public struct MBI { public long BaseAddress, AllocationBase; public uint AllocationProtect, Pad0; public long RegionSize; public uint State, Protect, Type, Pad1; }
    [System.Runtime.InteropServices.DllImport("kernel32", SetLastError = true)] public static extern nint OpenProcess(int access, bool inherit, int pid);
    [System.Runtime.InteropServices.DllImport("kernel32", SetLastError = true)] public static extern nint VirtualQueryEx(nint h, long addr, out MBI mbi, int size);
    [System.Runtime.InteropServices.DllImport("kernel32", SetLastError = true)] public static extern bool ReadProcessMemory(nint h, long addr, byte[] buf, long size, out long read);
}
