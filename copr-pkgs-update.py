#!/usr/bin/env python3
#
# Copyright 2022
#     Balint Cristian (cristian dot balint at gmail dot com)
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import sys
import time
import os, re
import subprocess
from copr.v3 import Client
from http import client as httplib


def helpmsg():
  print("Usage %s <projectname> [package]\n \
          [--force] Immediate force build\n \
          [--rebuild] Immediate rebuild (+nvr increment)\n \
          [--min-days    NUM] (default: 7)  Minumum amount of interval in days\n \
          [--cuda-builds NUM] (default: 1)  Maximum amount of cuda builds per session\n \
          [--cuda-ver-maj NUM] (default: 11)  CUDA version major\n \
          [--cuda-ver-min NUM] (default: 6)  CUDA version minor\n \
          [--fork <chroot-from-prefix> <chroot-into-prefix>] (example: --fork fedora-rawhide fedora-36)\n" \
         % sys.argv[0])
  exit(-1)

if len(sys.argv) < 2:
  helpmsg()

# default
mindays = 7
force = False
rebld = False
cudabuilds = -1
cu_ver_maj = None
cu_ver_min = None
coprproject = None
coprpackage = None
fork_from = None
fork_into = None

# parse extra args
for idx in range(1, len(sys.argv)):
  if (sys.argv[idx][0:2] == "--"):

    if (sys.argv[idx] == "--force"):
      force = True
      continue

    if (sys.argv[idx] == "--rebuild"):
      rebld = True
      continue

    if (sys.argv[idx] == "--min-days"):
      mindays = int(sys.argv[idx + 1])
      continue

    if (sys.argv[idx] == "--cuda-builds"):
      cudabuilds = int(sys.argv[idx + 1])
      continue

    if (sys.argv[idx] == "--cuda-ver-maj"):
      cu_ver_maj = int(sys.argv[idx + 1])
      continue

    if (sys.argv[idx] == "--cuda-ver-min"):
      cu_ver_min = int(sys.argv[idx + 1])
      continue

    if (sys.argv[idx] == "--fork"):
      fork_from = str(sys.argv[idx + 1])
      fork_into = str(sys.argv[idx + 2])
      continue

    print("Unknown arg: %s" % sys.argv[idx])
    helpmsg()

  else:

    if (idx < 3):

      if (not coprproject):
        coprproject = sys.argv[idx]
        continue

      if (coprproject and not coprpackage):
        coprpackage = sys.argv[idx]
        continue

      print("Unknown arg: %s" % sys.argv[idx])
      helpmsg()

client = Client.create_from_config_file()

def verMap(v):
    if not v: return tuple()
    return tuple(map(int, (v.split("."))))

def tagExtract(v, d = '-'):

  def tagNormal(t):
    if (t):
      # remove any last dot
      if (t[-1] == '.'): t = t[:-1]
      # remove any first dot
      if (t[ 0] == '.'): t = t[1: ]
    return t

  # delimit
  v = re.sub('[+,_]', '.', v, 0)
  # iterate
  while (True):
    if not v: return None
    # keep only literal parts
    for t in v.split('%s' % d):
      # skip empty
      if not t: continue
      # skip non literal
      if not re.findall('[0-9]', t):
        v = v.replace(t,''); break
      # literal segment tag
      m = re.findall('[a-z,A-Z]', t)
      if len(m):
        # lookup sub-segment
        v = t; d = m[0]; break
      else: return tagNormal(t)

  return tagNormal(t)

def httpRequest(method, host, uri, body=None):

    c = httplib.HTTPSConnection(host)
    headers = {
        "Connection": "keep-alive"
    }

    if body != None:
        headers["Content-Type"] = "applicaton/xml"
        headers["Content-Length"] = str(len(body))

    c.request(method, uri, body, headers)
    r = c.getresponse()

    if r.status != 200:
        print("    HTTP error: [%s]" % r.reason)
        return None

    bytes = r.read().decode(encoding='utf-8', errors='strict')

    return bytes

def gitCoprSpec(user, coprproject, pkgname, proto = "git"):

    spec = None

    if (proto == "git"):

      os.system("rm -rf /tmp/%s.copr" % pkgname)
      os.system("git clone -q https://copr-dist-git.fedorainfracloud.org/git/%s/%s/%s.git \
                        /tmp/%s.copr" % (user, coprproject, pkgname, pkgname))

      try:
        with open("/tmp/%s.copr/%s.spec" % (pkgname, pkgname)) as f:
          spec = f.read()
        os.system("rm -rf /tmp/%s.copr" % pkgname)
        return spec

      except:
        return None

    if (proto == "http"):

      spec = httpRequest("GET", "copr-dist-git.fedorainfracloud.org",
                         "/cgit/%s/%s/%s.git/plain/%s.spec"
           % (client.config['username'], coprproject, pkgname, pkgname))

      return spec

    print("Unknown protocol [%s]" % proto)
    exit(-1)


def gitCheckVersion(pkgname, branch, screpo, schash, dover = False):

    os.system("rm -rf /tmp/%s" % pkgname)
    os.system("git clone -q -n --filter=blob:none --depth 1 -b %s %s /tmp/%s" % (branch, screpo, pkgname))
    cmd = "git -C /tmp/%s log -1 --format=fuller --date=format:'%%Y%%m%%d%%H%%M' \
               | grep CommitDate | awk '{print $2}'" % pkgname
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    commitdate = proc.stdout.read().decode('utf-8').split()

    if (not commitdate):
        print("    GIT error fetching commitdate [%s]" % screpo)
        exit(-1)

    results = None
    logvers = None
    tagvers = None

    if (not dover):
      os.system("rm -rf /tmp/%s" % pkgname)
      return (logvers, tagvers, commitdate[0])

    # fetch last blob only
    os.system("git -C /tmp/%s fetch -q -n --filter=blob:none --depth 1 --tags 2>/dev/null" % pkgname)

    # extract release tag info
    cmd = "git -C /tmp/%s describe --tags --exact-match --candidates=1000000 %s 2>/dev/null" % (pkgname, schash)

    maxcount = 16
    while ( True ):
      if not maxcount: break
      # GITLOG: iterate through shallow fetches
      proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
      proc.wait()
      if proc.returncode:
        maxcount -= 1
        os.system("git -C /tmp/%s fetch -q -n --filter=blob:none --deepen 100 2>/dev/null" % pkgname)
      else:
        entry = proc.stdout.read().decode('utf-8').split()
        # extract tag part
        logvers = tagExtract(entry[0])
        break

    # GITTAG: just return a table of tags
    cmd = "git -C /tmp/%s tag --sort=creatordate 2>/dev/null" % pkgname
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    try:
      results = proc.stdout.read().decode('utf-8').split()
    except:
      results = None

    for idx, vers in enumerate(reversed(results)):

      # blacklists
      if ("gklib" in pkgname): continue
      if ("nextpnr" in pkgname): continue
      if ("bladerf" in pkgname and "_" in vers): continue
      if ("limesuite" in pkgname and "-" in vers): continue
      if ("onednn" in pkgname and "graph" in vers): continue
      if ("gnuradio" in pkgname and int(vers.split('.')[1]) < 11): continue
      if ("torch" in pkgname and "." not in vers): continue
      if ("libxsmm" in pkgname and re.findall('[a-z;A-Z]', vers)): continue
      if ("mxnet" in pkgname and int(vers.split('.')[0]) < 2): continue
      if ("optuna" in pkgname and int(re.sub('[a-z,A-Z]','',vers.split('.')[0],0)) < 3): continue
      if ("xbyak" in pkgname and len(vers) > 5): vers = vers[:5]

      # extract tag part
      tagvers = tagExtract(vers)
      if (tagvers): break

    os.system("rm -rf /tmp/%s" % pkgname)

    return (logvers, tagvers, commitdate[0])

def unpackSPEC(spec):

    f = open('/tmp/unpack.spec', 'w')
    f.write(spec)
    f.close()

    cmd = "rpmspec -P /tmp/unpack.spec"
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    unspec = proc.stdout.read().decode('utf-8')
    os.system("rm -rf /tmp/unpack.spec")

    return unspec


def buildNewSRPM(pkgname, newvers, newdate, newhash, newtags, pkgver):

    os.system("rm -rf /tmp/srpm-%s /tmp/srpm.tar" % pkgname)
    coprscm = "https://copr-dist-git.fedorainfracloud.org/git/%s/%s/%s.git /tmp/srpm-%s" \
            % (client.config['username'], coprproject, pkgname, pkgname)
    os.system("git clone -q --depth 1 -b master %s" % coprscm)

    # remove SPECPARTS
    os.system("sed -i '/rm -rf %%{_builddir}/d' /tmp/srpm-%s/*.spec;" % pkgname)
    os.system("sed -i '/SPECPARTS/d' /tmp/srpm-%s/*.spec;" % pkgname)

    if (newvers[0]):
      os.system("sed -i '/^Version:/s/.*/Version:        %s/' /tmp/srpm-%s/*.spec" % (newvers[0], pkgname))

    os.system("sed -i '/^%%global pkgvers/s/.*/%%global pkgvers %i/' /tmp/srpm-%s/*.spec" % (pkgver, pkgname))

    for i in range(0, len(newdate)):
      os.system("sed -i '/^%%global scdate%i/s/.*/%%global scdate%i %s/' /tmp/srpm-%s/*.spec" % (i, i, newdate[i][0:8], pkgname))

    for i in range(0, len(newhash)):
      if not newhash[i]: continue
      os.system("sed -i '/^%%global schash%i/s/.*/%%global schash%i %s/' /tmp/srpm-%s/*.spec" % (i, i, newhash[i], pkgname))

    for i in range(0, len(newtags)):
      if not newtags[i]: continue
      os.system("sed -i '/^%%global sctags%i/s/.*/%%global sctags%i %s/' /tmp/srpm-%s/*.spec" % (i, i, newtags[i].replace('/',r'\/'), pkgname))

    if (cu_ver_maj != None):
      os.system("sed -i '/^%%global vcu_maj/s/.*/%%global vcu_maj %s/' /tmp/srpm-%s/*.spec" % (cu_ver_maj, pkgname))

    if (cu_ver_min != None):
      os.system("sed -i '/^%%global vcu_min/s/.*/%%global vcu_min %s/' /tmp/srpm-%s/*.spec" % (cu_ver_min, pkgname))

    # look for any tarball payload
    cmd = "cat /tmp/srpm-%s/sources" % pkgname
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    # fetch tarballs (if any) from cloud
    for line in proc.stdout.readlines():
      srchash = line.decode('utf-8').split()[0]
      srcname = line.decode('utf-8').split()[1]
      os.system("curl https://copr-dist-git.fedorainfracloud.org/repo/pkgs/%s/%s/%s/%s/md5/%s/%s -o /tmp/srpm-%s/%s >/dev/null 2>&1" \
          % (client.config['username'], coprproject, pkgname, srcname, srchash, srcname, pkgname, srcname))

    # build final srpm
    cmd = "rpmbuild --define '_sourcedir /tmp/srpm-%s' --undefine dist -bs /tmp/srpm-%s/*.spec | grep Wrote" % (pkgname, pkgname)
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    srpm = proc.stdout.read().decode('utf-8').split()[1]
    os.system("rm -rf /tmp/srpm-%s" % pkgname)

    return srpm

def buildCOPR(srpm, chroots):

  cmd = "copr build %s --nowait --timeout 172800 %s" % (coprproject, srpm)
  for root in chroots:
    cmd += " -r %s" % root

  os.system(cmd)
  os.system("rm -rf /tmp/%s" % srpm)

# fetch project packages
pkglist = client.package_proxy.get_list(client.config['username'], coprproject, None, with_latest_build=True)
# fetch project enabled chroots
prjconf = client.project_proxy.get(client.config['username'], coprproject)
chroots = list(prjconf['chroot_repos'].keys() )

cuda_build = 0
idx = len(pkglist)
for pkg in pkglist:

  if(coprpackage and (pkg['name'] != coprpackage)):
    continue

  pkgname = pkg['name']
  print("%s/%s Checking [%s]" % (idx, len(pkglist), pkgname))

  idx = idx - 1

  state = pkg['builds']['latest']['state']
  version = pkg['builds']['latest']['source_package']['version']

  # skip non scm/tag
  if (len(version.split('-')[1].split('.')[0]) != 8):
    print("    UNVERSIONED [%s] [%s] is skipped" % (pkgname,version))
    continue

  # skip unfinished
  if (state != "succeeded"):
    print("    %s build [%s] holds the queue" % (state.upper(), version))
    continue

  difftime = int(time.time()) - int(pkg['builds']['latest']['submitted_on'])
  diffdays, diffhours = divmod(difftime, 86400)
  diffhours = divmod(diffhours, 3600)[0]

  if ( diffdays < mindays ) and not (force or rebld):
    print("    SKIP [%s] only [%sd %sh] /%sd" % (pkgname, diffdays, diffhours, mindays))
    continue

  # fetch latest .spec file form COPR cloud
  spec = gitCoprSpec(client.config['username'], coprproject, pkgname)
  if (not spec):
    print("    ERROR getting %s.spec" % pkgname)
    continue

  # parse spec file
  pkgver = re.findall('%global pkgvers (.+)', spec)

  if (not pkgver):
    print("    UNMANAGED n-v-r [%s] [%s] is skipped" % (pkgname, version))
    continue

  # skip locked spec
  lockver = re.findall('%global lockver (.+)', spec)

  if (lockver):
    print("    LOCKED n-v-r [%s] [%s] is skipped" % (pkgname, version))
    continue

  # check versions
  pkgrel = re.findall('Version: (.+)', spec)[0].split()[0]
  pkgver = int(re.findall('%global pkgvers (.+)', spec)[0])

  # self versioned package
  if "(" in pkgrel: pkgrel = None

  # check cuda requirements
  cudaver_maj = re.findall('%global vcu_maj (.+)', spec)
  cudaver_min = re.findall('%global vcu_min (.+)', spec)

  screpo = []
  scdate = []
  schash = []
  sctags = []
  branch = []
  scfilt = []

  newvers = []
  newdate = []
  newhash = []
  newtags = []

  stdout = None
  exit_code = 0

  for i in range(10):

    try:
      # look for tag-base versioning
      sctags.append(re.findall('%%global sctags%i (.+)' % i, spec)[0])
      screpo.append(re.findall('%%global source%i (.+)' % i, spec)[0])
      scdate.append(re.findall('%%global scdate%i (.+)' % i, spec)[0])
      try: scfilt.append(re.findall('%%global scfilt%i (.+)' % i, spec)[0])
      except: scfilt.append('')
      # tag filter mode
      filt = '| grep "%s" | sed "s|^{}||g"' % scfilt[i]
      # get upstream latest tag
      cmd = 'git ls-remote --tags --sort=version:refname %s %s | cut -d"/" -f3- | cut -d"^" -f1 | tail --lines=1' % (screpo[i], filt)
      proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
      try:
        stdout, stderr = proc.communicate(timeout=30)
        exit_code = proc.wait()
      except:
        proc.kill()
        exit_code = -1
      if (exit_code == 0):
        if len(stdout) == 0: exit_code = -2
        newtags.append(stdout.decode('utf-8').split()[0])
    except:
      newtags.append(None)

    try:
      # fall to hash-base versioning
      schash.append(re.findall('%%global schash%i (.+)' % i, spec)[0])
      screpo.append(re.findall('%%global source%i (.+)' % i, spec)[0])
      scdate.append(re.findall('%%global scdate%i (.+)' % i, spec)[0])
      branch.append(re.findall('%%global branch%i (.+)' % i, spec)[0])
      try: scfilt.append(re.findall('%%global scfilt%i (.+)' % i, spec)[0])
      except: scfilt.append('')
      # tag filter mode
      filt = '| grep "%s" | sed "s|^{}||g"' % scfilt[i]
      # get upstream latest hash
      cmd = 'git ls-remote --ref --head %s %s %s' % (screpo[i], branch[i], filt)
      proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
      try:
        stdout, stderr = proc.communicate(timeout=30)
        exit_code = proc.wait()
      except:
        proc.kill()
        exit_code = -1
      if (exit_code == 0):
        if len(stdout) == 0: exit_code = -3
        newhash.append(stdout.decode('utf-8').split()[0])
    except:
      newhash.append(None)
      if not newtags[i]: break

  if (exit_code != 0):
    print("    ERROR [%i] fetching [%s] repository" % (exit_code, screpo[i]))
    continue

  if ((newhash[0] and (schash[0] == newhash[0]))
   or (newtags[0] and (sctags[0] == newtags[0]))):
    # increment revision
    if rebld: pkgver = pkgver + 1
    elif force: pass
    else:
      if newhash[0]: print("    SKIP [%s] @ [%s] hash already latest" % (schash[0], scdate[0]))
      if newtags[0]: print("    SKIP [%s] @ [%s] tag already latest" % (sctags[0], scdate[0]))
      continue
  else:
    pkgver = 0

  if not (force or rebld) and ((cudaver_maj or cudaver_min)
    and (cudabuilds != -1) and (cuda_build >= cudabuilds)):
    # already queued one
    print("    SKIP [%s] [%s] reached %s CUDA build limit" % (pkgname, version, cudabuilds))
    continue

  #
  # new changes upstream
  #

  if not pkgrel:
    selfvers = re.findall('Version: (.+)', unpackSPEC(spec))[0].split()[0]
    print("    SELF versioned:[%s]" % selfvers)

  for i in range(0, len(screpo)):

    if (not newhash[i] and not newtags[i]):
      print("    Error getting newhash or newtag")
      exit(-1)

    # lookup v-r
    if newhash[i]:
      logvers, tagvers, ndate = gitCheckVersion(pkgname, branch[i], screpo[i], newhash[i], (i == 0) and pkgrel)
    if newtags[i]:
      logvers, tagvers, ndate = gitCheckVersion(pkgname, newtags[i], screpo[i], newtags[i], False)
      tagvers = tagExtract(newtags[i])

    # extract vers/date
    newvers.append(None)
    newdate.append(ndate)
    if (i == 0) and pkgrel:
      if newhash[i]: print("    NEW [%s] -> [%s] @ [%s](hash)" % (newdate[i][0:8], scdate[i], schash[i]))
      if newtags[i]: print("    NEW [%s] -> [%s] @ [%s](tags)" % (newdate[i][0:8], scdate[i], sctags[i]))
      error = 0
      if logvers and (verMap(logvers) > verMap(pkgrel)):
        # use logvers (default)
        newvers[i] = logvers
        print("    UPDATE version:[%s] -> [%s] @ [%s] (git logs)" % (newvers[i], pkgname, pkgrel))
      elif tagvers and (verMap(tagvers) > verMap(pkgrel)):
        # use tagvers (fallback)
        newvers[i] = tagvers
        print("    UPDATE version:[%s] -> [%s] @ [%s] (git tags)" % (newvers[i], pkgname, pkgrel))
      # pass if no changes
      elif logvers == pkgrel: pass
      elif tagvers == pkgrel: pass
      # pass on inexistent
      elif (not logvers) and (not tagvers): pass
      else:
        # check decreasing changes
        if logvers and (verMap(logvers) < verMap(pkgrel)):
          print("    ERROR: version decreasing: [%s] -> [%s] (git log)" % (logvers, pkgrel))
          error = 1
        if tagvers and (verMap(tagvers) < verMap(pkgrel)):
          print("    ERROR: version decreasing: [%s] -> [%s] (git tag)" % (tagvers, pkgrel))
          error = 2
      # fail decreasing
      if (error): exit(1)

    print("    UPDATE scdate%i:[%s] -> [%s] @ [%s]" % (i, newdate[i][0:8], pkgname, scdate[i]))
    if newhash[i] and newhash[i] != schash[i]:
      print("    UPDATE schash%i:[%s] -> [%s] @ [%s]" % (i, newhash[i][0:8], pkgname, schash[i][0:8]))
    if newtags[i] and newtags[i] != sctags[i]:
      print("    UPDATE sctags%i:[%s] -> [%s] @ [%s]" % (i, newtags[i], pkgname, sctags[i]))

  # build srpm
  srpm = buildNewSRPM(pkgname, newvers, newdate, newhash, newtags, pkgver)

  # add targets
  builders = []
  for chroot in pkg['builds']['latest']['chroots']:
    if chroot in chroots:
      builders.append(chroot)
      if (fork_into and (fork_from in chroot)):
        if not any(fork_into in s for s in pkg['builds']['latest']['chroots']):
          builders.append(chroot.replace(fork_from, fork_into))
          print("    APPEND active [%s] builder" % builders[-1])
    else:
      print("    SKIP inactive [%s] builder" % chroot)

  # submit build
  print("    SUBMIT [%s]" % srpm)
  buildCOPR(srpm, builders)

  # mark one cuda build
  if (cudaver_maj or cudaver_min): cuda_build += 1
