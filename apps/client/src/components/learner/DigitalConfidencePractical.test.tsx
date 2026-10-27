import {render,screen,fireEvent,act,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {DigitalConfidencePractical} from './DigitalConfidencePractical';
import content from '../../generated/publicCurriculumChunks/DIGITAL_CONFIDENCE.json';
afterEach(()=>vi.unstubAllGlobals());
it('a delayed file read preserves answers entered while bytes were loading',async()=>{
 let finish!:(text:string)=>void;let submitted:any;
 const text=new Promise<string>(resolve=>{finish=resolve;});
 vi.stubGlobal('fetch',vi.fn(async(url:string,init?:RequestInit)=>{
  if(url.includes('/cases/'))return {ok:true,json:async()=>({token:'fixture.token',expires:Math.floor(Date.now()/1000)+100,parameters:{filename:'case.txt',restored_filename:'restore.txt',size:256,used:180,reserved:12}})};
  submitted=JSON.parse(init!.body as string);return {ok:true,json:async()=>({checks:[],checks_passed:false,human_review:'pending'})};
 }));
 render(<DigitalConfidencePractical delivery={content.delivery!} unit={11}/>);
 fireEvent.click(screen.getByRole('button',{name:'Request fresh independent case'}));
 const chooser=await screen.findByLabelText('Choose your independently renamed note');
 const file=new File(['fictional'],'case.txt',{type:'text/plain'});Object.defineProperty(file,'text',{value:()=>text});
 fireEvent.change(chooser,{target:{files:[file]}});
 fireEvent.change(screen.getByLabelText('Independent usable free percentage'),{target:{value:'25'}});
 await act(async()=>{finish('fictional');await text;});
 expect(screen.getByLabelText('Independent usable free percentage')).toHaveValue(25);
 fireEvent.click(screen.getByRole('button',{name:'Check practical evidence'}));
 await waitFor(()=>expect(submitted.answers.free_percent).toBe('25'));
 expect(submitted.answers.renamed).toEqual({name:'case.txt',text:'fictional'});
});
