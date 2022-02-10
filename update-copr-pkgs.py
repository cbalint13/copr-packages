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
cudabuilds = 1
cu_ver_maj = None
cu_ver_min = None
coprproject = None
coprpackage = None
fork_from = None
fork_into = None

# parse extra args
for idx in range(1, len(sys.argv)):
  if (sys.argv[idx][0:2] == "--"):

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

def tagExtract(v, d = '-'):

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
      else: return t

  return t

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

def gitCheckVersion(pkgname, branch, screpo, dover = False):

    os.system("rm -rf /tmp/%s" % pkgname)
    os.system("git clone -q -n --filter=blob:none --depth 1 -b %s %s /tmp/%s" % (branch, screpo, pkgname))
    cmd = "git -C /tmp/%s log -1 --format=fuller --date=format:'%%Y%%m%%d%%H%%M' \
               | grep CommitDate | awk '{print $2}'" % pkgname
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    commitdate = proc.stdout.read().decode('utf-8').split()

    if (not commitdate):
        print("    GIT error fetching commitdate [%s]" % screpo)
        exit(-1)

    commitvers = None

    if (not dover):
      os.system("rm -rf /tmp/%s" % pkgname)
      return (commitvers, commitdate[0])

    # extract release tag info
    os.system("git -C /tmp/%s fetch -q -n --filter=blob:none --depth 1 --tags" % pkgname)
    cmd = "git -C /tmp/%s tag --sort=creatordate 2>/dev/null" % pkgname
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    try:
      results = proc.stdout.read().decode('utf-8').split()
    except:
      results = None

    for idx, vers in enumerate(reversed(results)):

      # blacklists
      if ("gcc" in pkgname): continue
      if ("gklib" in pkgname): continue
      if ("bladerf" in pkgname and "_" in vers): continue
      if ("limesuite" in pkgname and "-" in vers): continue
      if ("onednn" in pkgname and "graph" in vers): continue
      if ("gdb" in pkgname and "binutils" in vers): continue
      if ("binutils" in pkgname and "gdb" in vers): continue
      if ("newlib" in pkgname and "snapshot" in vers): continue
      if ("newlib" in pkgname and "newlib" not in vers): continue

      # delimit
      vers = re.sub('[+,_]', '.', vers, 0)

      # extract tag part
      commitvers = tagExtract(vers)

      if (commitvers):
        # remove any last dot
        if (commitvers[-1] == '.'):
          commitvers = commitvers[:-1]
        # stop
        break
      else:
        # next
        continue

    os.system("rm -rf /tmp/%s" % pkgname)

    return (commitvers, commitdate[0])

def buildNewSRPM(pkgname, newvers, newdate, newhash):

    os.system("rm -rf /tmp/srpm-%s /tmp/srpm.tar" % pkgname)
    coprscm = "https://copr-dist-git.fedorainfracloud.org/git/%s/%s/%s.git /tmp/srpm-%s" \
            % (client.config['username'], coprproject, pkgname, pkgname)
    os.system("git clone -q --depth 1 -b master %s" % coprscm)

    if (newvers[0]):
      os.system("sed -i '/^Version:/s/.*/Version:        %s/' /tmp/srpm-%s/*.spec" % (newvers[0], pkgname))

    for i in range(0, len(newhash)):
      os.system("sed -i '/^\%%global pkgvers/s/.*/\%%global pkgvers 0/' /tmp/srpm-%s/*.spec" % pkgname)
      os.system("sed -i '/^\%%global scdate%i/s/.*/\%%global scdate%i %s/' /tmp/srpm-%s/*.spec" % (i, i, newdate[i][0:8], pkgname))
      os.system("sed -i '/^\%%global schash%i/s/.*/\%%global schash%i %s/' /tmp/srpm-%s/*.spec" % (i, i, newhash[i], pkgname))

    if (cu_ver_maj):
      os.system("sed -i '/^\%%global vcu_maj/s/.*/\%%global vcu_maj %s/' /tmp/srpm-%s/*.spec" % (cu_ver_maj, pkgname))

    if (cu_ver_min):
      os.system("sed -i '/^\%%global vcu_min/s/.*/\%%global vcu_min %s/' /tmp/srpm-%s/*.spec" % (cu_ver_min, pkgname))

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

  # skip non scm
  if (not ".git" in version):
    print("    PINNED [%s] [%s] is skipped" % (pkgname,version))
    continue
  # skip unfinished
  if (state != "succeeded"):
    print("    %s build [%s] holds the queue" % (state.upper(), version))
    continue

  difftime = int(time.time()) - int(pkg['builds']['latest']['submitted_on'])
  diffdays, diffhours = divmod(difftime, 86400)
  diffhours = divmod(diffhours, 3600)[0]

  if ( diffdays < mindays ):
    print("    SKIP [%s] only [%sd %sh] /%sd" % (pkgname, diffdays, diffhours, mindays))
    continue

  # fetch latest .spec file form COPR cloud
  spec = httpRequest("GET", "copr-dist-git.fedorainfracloud.org",
                     "/cgit/%s/%s/%s.git/plain/%s.spec"
          % (client.config['username'], coprproject, pkgname, pkgname))
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

  pkgrel = re.findall('Version: (.+)', spec)[0].split()[0]

  # check cuda requirements
  cudaver_maj = re.findall('%global vcu_maj (.+)', spec)
  cudaver_min = re.findall('%global vcu_min (.+)', spec)


  screpo = []
  scdate = []
  schash = []
  branch = []

  newvers = []
  newdate = []
  newhash = []

  for i in range(10):

    try:
      screpo.append(re.findall('%%global source%i (.+)' % i, spec)[0])
      scdate.append(re.findall('%%global scdate%i (.+)' % i, spec)[0])
      schash.append(re.findall('%%global schash%i (.+)' % i, spec)[0])
      branch.append(re.findall('%%global branch%i (.+)' % i, spec)[0])

    except:
      break

    # get upstream latest hash
    cmd = 'git ls-remote --ref --head %s %s' % (screpo[i], branch[i])
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    newhash.append(proc.stdout.read().decode('utf-8').split()[0])

  if (schash[0] == newhash[0]):
    # already updated
    print("    SKIP [%s] @ [%s] already latest" % (scdate[0], schash[0]))
    continue

  else:

    if ((cudaver_maj or cudaver_min)
      and (cuda_build >= cudabuilds)):
      # already queued one
      print("    SKIP [%s] [%s] reached %s CUDA build limit" % (pkgname, version, cudabuilds))
      continue

    # new changes upstream
    for i in range(0, len(screpo)):

      # lookup v-r
      nvers, ndate = gitCheckVersion(pkgname, branch[i], screpo[i], i == 0)

      newvers.append(nvers)
      newdate.append(ndate)

      if (i == 0):
        print("    NEW [%s] -> [%s] @ [%s]" % (newdate[i][0:8], scdate[i], schash[i]))
        print("    UPDATE version:[%s] -> [%s] @ [%s]" % (newvers[i], pkgname, pkgrel))

      print("    UPDATE scdate%i:[%s] -> [%s] @ [%s]" % (i, newdate[i][0:8], pkgname, scdate[i]))
      print("    UPDATE schash%i:[%s] -> [%s] @ [%s]" % (i, newhash[i][0:8], pkgname, schash[i][0:8]))

    # build srpm
    srpm = buildNewSRPM(pkgname, newvers, newdate, newhash)

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
